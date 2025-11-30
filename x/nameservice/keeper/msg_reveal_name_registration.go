package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	"dysonprotocol.com/x/nft"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// Reveal completes name registration by revealing the committed name and salt.
//
// Semantics:
//   - Completes commit-reveal scheme by validating the revealed name matches the commitment hash.
//   - Mints a new Name NFT with the revealed name as NFT ID.
//   - Charges annual valuation fee based on committed valuation and class parameters.
//   - Sets up NFT data with valuation, expiry, and default listing status.
//   - Creates reverse mapping from owner address to name for resolution.
//
// Validation:
//   - Committer address must be valid bech32.
//   - Name cannot be empty and must match name format regex (lowercase, alphanumeric+dashes, ends with .dys).
//   - Name must not already be registered.
//   - Commitment must exist for the computed hash (name + committer + salt).
//   - Revealed committer must match commitment owner.
//   - Valuation from commitment must be valid and non-zero.
//
// State Updates:
//   - Mints new NFT in nameservice.dys class with revealed name as ID.
//   - Sets NFT data with valuation, expiry (based on class valuation period), and metadata.
//   - Creates reverse name-to-address mapping for resolution.
//   - Deletes the used commitment.
//   - Charges annual valuation fee to community pool.
//
// Emits:
//   - EventNameRegistered(name, fee) on successful name registration.
//
// Returns:
//   - *nameservicev1.MsgRevealResponse (empty response indicating success).
//
// Errors are returned on invalid parameters, name format issues, duplicate names, missing commitments, or fee calculation failures; no panics.
func (k Keeper) Reveal(ctx context.Context, msg *nameservicev1.MsgReveal) (*nameservicev1.MsgRevealResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Validate addresses
	committerAddr, err := sdk.AccAddressFromBech32(msg.Committer)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid committer address: %s", msg.Committer)
	}

	// Validate name is not empty
	if msg.Name == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "name cannot be empty")
	}

	// Validate that the name follows the format: lowercase alphanumeric, starts with letter, may contain dashes, ends with ".dys"
	if !nameservicev1.NameRegex.MatchString(msg.Name) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid name format: must be lowercase, start with a letter, contain only alphanumeric and dash characters, and end with .dys")
	}

	// Check if name is already registered
	if k.nftKeeper.HasNFT(ctx, NamesClassID, msg.Name) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "name is already registered")
	}

	// Calculate hash using the common hash function
	hexhash := k.ComputeNameRegistrationHash(msg.Name, msg.Committer, msg.Salt)

	// Get the commitment
	commitment, err := k.GetCommitment(ctx, hexhash)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "commitment not found")
	}

	// Validate commitment has not expired
	if sdkCtx.BlockTime().Sub(commitment.Timestamp) > CommitmentTTL {
		// Delete the expired commitment
		_ = k.DeleteCommitment(ctx, hexhash)
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "commitment has expired (older than 1 hour)")
	}

	// Validate committer matches commitment
	if commitment.Owner != msg.Committer {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrUnauthorized, "committer does not match commitment")
	}

	// Ensure the Names NFT class exists before calculating fees
	if err := k.EnsureNamesClassExists(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to ensure names NFT class exists")
	}

	// Use the valuation from the commitment
	valuation := commitment.Valuation

	// Validate that the valuation is not zero after assignment
	if valuation.IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "valuation cannot be zero - please set a valuation in the commitment")
	}

	// Validate the valuation
	err = k.ValidateValuation(ctx, NamesClassID, valuation)
	if err != nil {
		return nil, err
	}

	// Calculate and charge the annual fee based on the valuation
	var fee sdk.Coins

	// Get the NFT class data for fee calculation and expiry
	classData, err := k.GetNFTClassData(ctx, NamesClassID)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to get nameservice NFT class data for fee calculation")
	}

	// Get the annual fee percentage from the class data
	feePercentStr := classData.ValuationFeePct
	if feePercentStr == "" {
		feePercentStr = "0"
	}

	// Convert the percentage string to a decimal
	feePercent, err := math.LegacyNewDecFromStr(feePercentStr)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to parse annual valuation fee percent")
	}

	if !feePercent.IsZero() {
		// Convert the single coin to a DecCoins for precise math operations
		decValuation := sdk.NewDecCoinsFromCoins(valuation)

		// Convert to LegacyDec for compatibility with SDK DecCoins methods
		legacyFeePercent, err := math.LegacyNewDecFromStr(feePercent.String())
		if err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to convert to legacy decimal")
		}

		// Calculate fee by multiplying the valuation by fee percentage
		decFees := decValuation.MulDec(legacyFeePercent)

		// Convert back to regular Coins for blockchain transactions
		fee, _ = decFees.TruncateDecimal()

		// Charge the fee
		if !fee.IsZero() {
			err = k.communityPoolKeeper.FundCommunityPool(ctx, fee, committerAddr.Bytes())
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to send fee to community pool")
			}
		}
	}

	// Create NFT data with expiry based on class valuation_period
	period := classData.ValuationPeriod
	if period <= 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "valuation_period not set for class %s", NamesClassID)
	}
	nftData := &nameservicev1.NFTData{
		Listed:          true,
		Valuation:       valuation,
		ValuationExpiry: sdkCtx.BlockTime().Add(period),
		Metadata:        "",
	}

	// Marshal the NFT data
	nftDataAny, err := codectypes.NewAnyWithValue(nftData)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to marshal NFT data")
	}

	// Create the NFT
	token := nft.NFT{
		ClassId: NamesClassID,
		Id:      msg.Name,
		Uri:     msg.Committer,
		UriHash: "",
		Data:    nftDataAny,
	}

	// Mint the NFT
	if err := k.nftKeeper.Mint(ctx, token, committerAddr); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to mint name NFT")
	}

	// Add reverse mapping for the newly registered name
	if msg.Committer != "" {
		if err := k.SetNameDestinationMapping(ctx, msg.Committer, msg.Name); err != nil {
			k.Logger.Error("Reveal: Failed to add reverse mapping", "destination", msg.Committer, "name", msg.Name, "error", err)
			// Don't fail the transaction for reverse mapping errors, just log
		} else {
			k.Logger.Info("Reveal: Added reverse mapping for new name", "destination", msg.Committer, "name", msg.Name)
		}
	}

	// Delete commitment
	err = k.DeleteCommitment(ctx, hexhash)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete commitment")
	}

	// Emit event
	err = sdkCtx.EventManager().EmitTypedEvent(
		&nameservicev1.EventNameRegistered{
			Name: msg.Name,
			Fee:  fee,
		})
	if err != nil {
		k.Logger.Error("failed to emit name registered event", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "failed to emit name registered event")
	}

	return &nameservicev1.MsgRevealResponse{}, nil
}
