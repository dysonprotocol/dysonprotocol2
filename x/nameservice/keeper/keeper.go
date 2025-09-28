package keeper

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	"cosmossdk.io/collections"
	"cosmossdk.io/core/store"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/log"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"

	nameservicev1 "dysonprotocol.com/x/nameservice/types"
)

var (
	// CommitmentsKey is the key for commitments
	CommitmentsKey = collections.NewPrefix(2)

	// ParamsKey is the key for parameters
	ParamsKey = collections.NewPrefix(4)

	// NameDestinationsKey is the key for reverse name->destination mappings
	NameDestinationsKey = collections.NewPrefix(5)

	// ClassesByRootNameKey is the key for reverse root-name -> class id mappings
	ClassesByRootNameKey = collections.NewPrefix(6)

	// DenomsByRootNameKey is the key for reverse root-name -> denom mappings
	DenomsByRootNameKey = collections.NewPrefix(7)

	// Bid ledger and indexes
	BidSeqKey          = collections.NewPrefix(8)
	BidsKey            = collections.NewPrefix(9)
	BidsByBidderKey    = collections.NewPrefix(10)
	BidsByNFTKey       = collections.NewPrefix(11)
	ActiveBidForNFTKey = collections.NewPrefix(12)
)

// Keeper defines the nameservice keeper
type Keeper struct {
	nameservicev1.UnimplementedMsgServer

	cdc                 codec.Codec
	storeService        store.KVStoreService
	bankKeeper          nameservicev1.BankKeeper
	accountKeeper       nameservicev1.AccountKeeper
	communityPoolKeeper nameservicev1.CommunityPoolKeeper
	nftKeeper           nameservicev1.NFTKeeper

	// Core services
	Logger log.Logger

	Schema      collections.Schema
	commitments collections.Map[string, nameservicev1.Commitment]
	params      collections.Item[nameservicev1.Params]

	// nameDestinations stores reverse mappings: (destination_address, source_name) -> source_name
	// This allows efficient querying of all names pointing to a destination address
	nameDestinations collections.Map[collections.Pair[string, string], string]

	// classesByRootName stores reverse mappings: (root_name, class_id) -> class_id
	// Enables listing all class IDs that belong to a root name
	classesByRootName collections.Map[collections.Pair[string, string], string]

	// denomsByRootName stores reverse mappings: (root_name, denom) -> empty string
	// Enables listing all denoms that belong to a root name; supply is read from bank if needed
	denomsByRootName collections.Map[collections.Pair[string, string], string]

	// Bid ledger
	bidSeq          collections.Sequence
	bids            collections.Map[uint64, nameservicev1.BidRecord]
	bidsByBidder    collections.Map[collections.Pair[string, uint64], uint64]
	bidsByNFT       collections.Map[collections.Triple[string, string, uint64], uint64]
	activeBidForNFT collections.Map[collections.Pair[string, string], uint64]

	authority string // the address that is authorized to update module parameters
}

// NewKeeper creates a new nameservice Keeper instance
func NewKeeper(
	cdc codec.Codec,
	storeService store.KVStoreService,
	bankKeeper nameservicev1.BankKeeper,
	accountKeeper nameservicev1.AccountKeeper,
	communityPoolKeeper nameservicev1.CommunityPoolKeeper,
	nftKeeper nameservicev1.NFTKeeper,
	logger log.Logger,
	authority string,
) Keeper {
	// Create schema builder
	sb := collections.NewSchemaBuilder(storeService)

	k := &Keeper{
		cdc:                 cdc,
		storeService:        storeService,
		bankKeeper:          bankKeeper,
		accountKeeper:       accountKeeper,
		communityPoolKeeper: communityPoolKeeper,
		nftKeeper:           nftKeeper,
		Logger:              logger,
		authority:           authority,
		commitments:         collections.NewMap(sb, CommitmentsKey, "commitments", collections.StringKey, codec.CollValue[nameservicev1.Commitment](cdc)),
		params:              collections.NewItem(sb, ParamsKey, "params", codec.CollValue[nameservicev1.Params](cdc)),
		nameDestinations:    collections.NewMap(sb, NameDestinationsKey, "name_destinations", collections.PairKeyCodec(collections.StringKey, collections.StringKey), collections.StringValue),
		classesByRootName:   collections.NewMap(sb, ClassesByRootNameKey, "classes_by_root_name", collections.PairKeyCodec(collections.StringKey, collections.StringKey), collections.StringValue),
		denomsByRootName:    collections.NewMap(sb, DenomsByRootNameKey, "denoms_by_root_name", collections.PairKeyCodec(collections.StringKey, collections.StringKey), collections.StringValue),
	}

	// Bid ledger collections
	k.bidSeq = collections.NewSequence(sb, BidSeqKey, "bid_seq")
	k.bids = collections.NewMap(sb, BidsKey, "bids", collections.Uint64Key, codec.CollValue[nameservicev1.BidRecord](cdc))
	k.bidsByBidder = collections.NewMap(
		sb,
		BidsByBidderKey,
		"bids_by_bidder",
		collections.PairKeyCodec(collections.StringKey, collections.Uint64Key),
		collections.Uint64Value,
	)
	k.bidsByNFT = collections.NewMap(
		sb,
		BidsByNFTKey,
		"bids_by_nft",
		collections.TripleKeyCodec(collections.StringKey, collections.StringKey, collections.Uint64Key),
		collections.Uint64Value,
	)
	k.activeBidForNFT = collections.NewMap(
		sb,
		ActiveBidForNFTKey,
		"active_bid_for_nft",
		collections.PairKeyCodec(collections.StringKey, collections.StringKey),
		collections.Uint64Value,
	)

	schema, err := sb.Build()
	if err != nil {
		panic(err)
	}

	k.Schema = schema

	return *k
}

// SetNameDestinationMapping adds a reverse mapping from destination address to source name
func (k Keeper) SetNameDestinationMapping(ctx context.Context, destination string, sourceName string) error {
	key := collections.Join(destination, sourceName)
	return k.nameDestinations.Set(ctx, key, sourceName)
}

// RemoveNameDestinationMapping removes a reverse mapping from destination address to source name
func (k Keeper) RemoveNameDestinationMapping(ctx context.Context, destination string, sourceName string) error {
	key := collections.Join(destination, sourceName)
	return k.nameDestinations.Remove(ctx, key)
}

// SetClassByRootName adds or updates a reverse mapping from root name to class ID
func (k Keeper) SetClassByRootName(ctx context.Context, rootName string, classID string) error {
	key := collections.Join(rootName, classID)
	return k.classesByRootName.Set(ctx, key, classID)
}

// RemoveClassByRootName removes a reverse mapping from root name to class ID
func (k Keeper) RemoveClassByRootName(ctx context.Context, rootName string, classID string) error {
	key := collections.Join(rootName, classID)
	return k.classesByRootName.Remove(ctx, key)
}

// setDenomTracked stores the denom under its root; value is empty string since supply comes from bank
func (k Keeper) setDenomTracked(ctx context.Context, denom string) error {
	return k.denomsByRootName.Set(ctx, collections.Join(extractRootName(denom), denom), "")
}

// unsetDenomTracked removes denom entry from reverse index
func (k Keeper) unsetDenomTracked(ctx context.Context, denom string) error {
	return k.denomsByRootName.Remove(ctx, collections.Join(extractRootName(denom), denom))
}

// GetNamesByDestination returns all names pointing to the given destination address
// Uses prefix iteration to efficiently find all names for a destination
func (k Keeper) GetNamesByDestination(ctx context.Context, destination string) ([]string, error) {
	var names []string

	// Create prefix range for the destination address
	rng := collections.NewPrefixedPairRange[string, string](destination)

	// Iterate over all entries with the destination prefix
	iter, err := k.nameDestinations.Iterate(ctx, rng)
	if err != nil {
		return nil, err
	}
	defer iter.Close()

	// Collect all the source names
	for ; iter.Valid(); iter.Next() {
		kv, err := iter.KeyValue()
		if err != nil {
			return nil, err
		}
		names = append(names, kv.Value)
	}

	return names, nil
}

// GetParams returns the current module parameters
func (k Keeper) GetParams(ctx context.Context) (params nameservicev1.Params) {
	params, err := k.params.Get(ctx)
	if err != nil {
		// If params don't exist, return defaults
		return nameservicev1.DefaultParams()
	}
	return params
}

// SetParams sets the module parameters
func (k Keeper) SetParams(ctx context.Context, params nameservicev1.Params) error {
	if err := params.Validate(); err != nil {
		return err
	}
	// Check if store service is accessible
	if k.storeService == nil {
		k.Logger.Error("SetParams: Store service is nil, cannot set params")
		return fmt.Errorf("store service is nil, cannot set parameters")
	}

	// Additional check to ensure store is initialized
	store := k.storeService.OpenKVStore(ctx)
	if store == nil {
		k.Logger.Error("SetParams: Failed to open KV store, store is nil")
		return fmt.Errorf("failed to open KV store, store is nil")
	}
	return k.params.Set(ctx, params)
}

// GetNFTData gets the NFTData for an NFT with the given class ID and NFT ID
func (k Keeper) GetNFTData(ctx context.Context, classId string, nftId string) (nameservicev1.NFTData, error) {
	k.Logger.Info("GetNFTData: Getting NFT data", "class_id", classId, "nft_id", nftId)

	nft, found := k.nftKeeper.GetNFT(ctx, classId, nftId)
	if !found {
		k.Logger.Error("GetNFTData: NFT not found", "class_id", classId, "nft_id", nftId)
		return nameservicev1.NFTData{}, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "NFT not found: %s", nftId)
	}

	k.Logger.Info("GetNFTData: Found NFT", "class_id", classId, "nft_id", nftId, "has_data", nft.Data != nil)

	nftData := nameservicev1.NFTData{}

	// Instead of using GetCachedValue() or UnpackAny, directly unmarshal the Value bytes
	k.Logger.Info("GetNFTData: Directly unmarshaling data", "class_id", classId, "nft_id", nftId)

	if nft.Data != nil {
		if err := k.cdc.Unmarshal(nft.Data.Value, &nftData); err != nil {
			k.Logger.Error("GetNFTData: Failed to unmarshal NFT data",
				"class_id", classId,
				"nft_id", nftId,
				"error", err,
				"type_url", nft.Data.TypeUrl,
				"value_len", len(nft.Data.Value))
			return nameservicev1.NFTData{}, cosmossdkerrors.Wrap(err, "failed to unmarshal NFT data")
		}
	}

	k.Logger.Info("GetNFTData: Successfully unmarshaled data", "class_id", classId, "nft_id", nftId, "listed", nftData.Listed)

	return nftData, nil
}

// GetNameOwner gets the owner of a name
func (k Keeper) GetNameOwner(ctx context.Context, name string) (string, bool) {
	if !k.nftKeeper.HasNFT(ctx, NamesClassID, name) {
		return "", false
	}

	owner := k.nftKeeper.GetOwner(ctx, NamesClassID, name)
	return owner.String(), true
}

// GetCommitment gets a commitment
func (k Keeper) GetCommitment(ctx context.Context, hexhash string) (nameservicev1.Commitment, error) {
	return k.commitments.Get(ctx, hexhash)
}

// SetCommitment sets a commitment
func (k Keeper) SetCommitment(ctx context.Context, commitment nameservicev1.Commitment) error {
	return k.commitments.Set(ctx, commitment.Hexhash, commitment)
}

// DeleteCommitment deletes a commitment
func (k Keeper) DeleteCommitment(ctx context.Context, hexhash string) error {
	return k.commitments.Remove(ctx, hexhash)
}

// GetAllCommitmentHashes returns all commitment hashes
func (k Keeper) GetAllCommitmentHashes(ctx context.Context) ([]string, error) {
	var hashes []string

	if err := k.commitments.Walk(ctx, nil, func(hexhash string, _ nameservicev1.Commitment) (bool, error) {
		hashes = append(hashes, hexhash)
		return false, nil
	}); err != nil {
		return nil, err
	}

	return hashes, nil
}

// GetAllCommitments returns all commitments
func (k Keeper) GetAllCommitments(ctx context.Context) ([]nameservicev1.Commitment, error) {
	var commitments []nameservicev1.Commitment

	if err := k.commitments.Walk(ctx, nil, func(_ string, commitment nameservicev1.Commitment) (bool, error) {
		commitments = append(commitments, commitment)
		return false, nil
	}); err != nil {
		return nil, err
	}

	return commitments, nil
}

// GetNFTClassData gets the NFTClassData for a class
func (k Keeper) GetNFTClassData(ctx context.Context, classID string) (nameservicev1.NFTClassData, error) {
	k.Logger.Info("GetNFTClassData: Getting class data", "class_id", classID)

	class, found := k.nftKeeper.GetClass(ctx, classID)
	if !found {
		k.Logger.Error("GetNFTClassData: Class not found", "class_id", classID)
		return nameservicev1.NFTClassData{}, cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "NFT class not found: %s", classID)
	}

	k.Logger.Info("GetNFTClassData: Found class", "class_id", classID, "name", class.Name, "has_data", class.Data != nil)

	var nftClassData nameservicev1.NFTClassData
	if class.Data != nil {
		// Instead of UnpackAny, directly unmarshal the Value bytes
		if err := k.cdc.Unmarshal(class.Data.Value, &nftClassData); err != nil {
			k.Logger.Error("GetNFTClassData: Failed to unmarshal NFT class data",
				"class_id", classID,
				"error", err,
				"type_url", class.Data.TypeUrl,
				"value_len", len(class.Data.Value))
			return nameservicev1.NFTClassData{}, cosmossdkerrors.Wrap(err, "failed to unmarshal class data")
		}

		k.Logger.Info("GetNFTClassData: Successfully unmarshaled data", "class_id", classID, "always_listed", nftClassData.AlwaysListed, "valuation_fee_pct", nftClassData.ValuationFeePct)

	} else {
		k.Logger.Info("GetNFTClassData: Class data is nil", "class_id", classID)
		nftClassData = nameservicev1.NFTClassData{}
	}

	return nftClassData, nil
}

// SetNFTClassData updates the class data for an NFT class
func (k Keeper) SetNFTClassData(ctx context.Context, classID string, classData nameservicev1.NFTClassData) error {
	// Get the NFT class
	class, found := k.nftKeeper.GetClass(ctx, classID)
	if !found {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "NFT class not found: %s", classID)
	}

	// Marshal the NFT class data to an Any
	classDataAny, err := codectypes.NewAnyWithValue(&classData)
	if err != nil {
		k.Logger.Error("SetNFTClassData: Failed to marshal NFT class data", "class", classID, "error", err)
		return cosmossdkerrors.Wrap(err, "failed to marshal NFT class data")
	}

	// Update the class
	class.Data = classDataAny
	if err := k.nftKeeper.UpdateClass(ctx, class); err != nil {
		k.Logger.Error("SetNFTClassData: Failed to update NFT class data", "class", classID, "error", err)
		return cosmossdkerrors.Wrap(err, "failed to update NFT class data")
	}

	return nil
}

// SetNFTData updates the NFT data for a classId/nftId
func (k Keeper) SetNFTData(ctx context.Context, classId string, nftId string, nftData nameservicev1.NFTData) error {
	// Get the NFT
	nft, found := k.nftKeeper.GetNFT(ctx, classId, nftId)
	if !found {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrNotFound, "NFT not found: %s", nftId)
	}

	// Marshal the NFT data to an Any
	nftDataAny, err := codectypes.NewAnyWithValue(&nftData)
	if err != nil {
		k.Logger.Error("SetNFTData: Failed to marshal NFT data", "class_id", classId, "nft_id", nftId, "error", err)
		return cosmossdkerrors.Wrap(err, "failed to marshal NFT data")
	}

	// Update the NFT
	nft.Data = nftDataAny
	if err := k.nftKeeper.Update(ctx, nft); err != nil {
		k.Logger.Error("SetNFTData: Failed to update NFT data", "class_id", classId, "nft_id", nftId, "error", err)
		return cosmossdkerrors.Wrap(err, "failed to update NFT data")
	}

	return nil
}

// ValidateValuation validates that a valuation coin meets all requirements:
// - not zero
// - has a denom
// - amount > 0
// - denom is in the allowed denoms list from params
func (k Keeper) ValidateValuation(ctx context.Context, classId string, valuation sdk.Coin) error {
	// Validate that the valuation is not zero
	if valuation.IsZero() {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "valuation cannot be zero")
	}

	// Validate denom is not empty
	if valuation.Denom == "" {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "valuation denom cannot be empty")
	}

	// Validate amount is greater than 0
	if valuation.Amount.IsZero() || valuation.Amount.IsNegative() {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "valuation amount must be greater than 0")
	}

	// Check if the valuation denomination is allowed by class configuration
	classData, err := k.GetNFTClassData(ctx, classId)
	if err != nil {
		return cosmossdkerrors.Wrap(err, "failed to get class data for valuation validation")
	}
	denomAllowed := false
	for _, denom := range classData.AllowedDenoms {
		if valuation.Denom == denom {
			denomAllowed = true
			break
		}
	}
	if !denomAllowed {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "valuation denomination is not allowed for this class")
	}

	return nil
}

// ComputeNameRegistrationHash computes the hash for a name registration using name, committer, and salt
func (k Keeper) ComputeNameRegistrationHash(name, committer, salt string) string {
	hash := sha256.Sum256([]byte(name + ":" + committer + ":" + salt))
	return hex.EncodeToString(hash[:])
}

// GetAuthority returns the module's authority
func (k Keeper) GetAuthority() string {
	return k.authority
}

// ResolveNameOrAddress takes a string that could be either a nameservice name or an address
// and returns the corresponding address. If it's an address, it returns it directly.
// If it's a nameservice name, it resolves it to an address iteratively following name chains.
func (k Keeper) ResolveNameOrAddress(ctx context.Context, nameOrAddress string) (string, error) {
	current := nameOrAddress
	visited := make(map[string]bool)
	maxDepth := 10 // Prevent infinite loops

	for i := 0; i < maxDepth; i++ {
		// Check if we've already visited this name to detect cycles
		if visited[current] {
			return "", cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
				fmt.Sprintf("circular name resolution detected for: %s", current))
		}

		// Check if the current value is already a valid address
		_, err := sdk.AccAddressFromBech32(current)
		if err == nil {
			// It's a valid address, return it as the final result
			return current, nil
		}

		// Mark this name as visited
		visited[current] = true

		// Try to resolve it as a nameservice name NFT
		nft, found := k.nftKeeper.GetNFT(ctx, NamesClassID, current)
		if !found {
			return "", cosmossdkerrors.Wrap(sdkerrors.ErrNotFound,
				fmt.Sprintf("name not found: %s", current))
		}

		// Update current to the resolved destination
		current = nft.Uri
	}

	// If we've reached max depth without resolving to an address
	return "", cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest,
		fmt.Sprintf("name resolution exceeded maximum depth of %d for: %s", maxDepth, nameOrAddress))
}

// ExportGenesis returns the exported genesis state as raw bytes for the gov
func (k Keeper) ExportGenesis(ctx context.Context) (*nameservicev1.GenesisState, error) {
	commitments, err := k.GetAllCommitments(ctx)
	if err != nil {
		return nil, err
	}

	gs := &nameservicev1.GenesisState{
		Params:      k.GetParams(ctx),
		Commitments: commitments,
	}
	// NOTE: Additional reverse-index or bid-ledger state is derived from other
	// modules and internal activity. We intentionally do not persist these in
	// genesis and instead rebuild them during InitGenesis to keep genesis minimal
	// and deterministic.
	return gs, nil
}
