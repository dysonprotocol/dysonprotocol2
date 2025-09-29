package keeper

import (
	"context"

	"cosmossdk.io/collections"
	"cosmossdk.io/core/store"
	"cosmossdk.io/math"

	"cosmossdk.io/errors"
	"cosmossdk.io/log"
	storage "dysonprotocol.com/x/storage"
	storagev1 "dysonprotocol.com/x/storage/types"
	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// We store each entry under "{owner}/{index}".
var StoragePrefix = collections.NewPrefix(0)
var ParamsKey = collections.NewPrefix(1)
var StorageMetricsPrefix = collections.NewPrefix(2)

type Keeper struct {
	config        storage.Config
	cdc           codec.Codec
	accKeeper     storage.AccountKeeper
	stakingKeeper storage.StakingKeeper
	namesvcKeeper storage.NameserviceKeeper
	authority     string // the address that is authorized to update module parameters

	Schema collections.Schema

	// The robust store-level map ({owner}/{index})->Storage
	StorageMap collections.Map[string, storagev1.Storage]
	// The storage metrics map: owner -> StorageMetrics
	StorageMetricsMap collections.Map[string, storagev1.StorageMetrics]
	params            collections.Item[storagev1.Params]
}

func NewKeeper(
	storeService store.KVStoreService,
	cdc codec.Codec,
	accKeeper storage.AccountKeeper,
	stakingKeeper storage.StakingKeeper,
	namesvcKeeper storage.NameserviceKeeper,
	config storage.Config,
	authority string,

) Keeper {
	sb := collections.NewSchemaBuilder(storeService)
	k := Keeper{
		config:        config,
		cdc:           cdc,
		accKeeper:     accKeeper,
		stakingKeeper: stakingKeeper,
		namesvcKeeper: namesvcKeeper,
		authority:     authority,
		StorageMap: collections.NewMap(
			sb,
			StoragePrefix, // prefix partition
			"storage_map", // name
			collections.StringKey,
			codec.CollValue[storagev1.Storage](cdc),
		),
		StorageMetricsMap: collections.NewMap(
			sb,
			StorageMetricsPrefix, // prefix partition
			"storage_metrics",    // name
			collections.StringKey,
			codec.CollValue[storagev1.StorageMetrics](cdc),
		),
		params: collections.NewItem(
			sb,
			ParamsKey,
			"params",
			codec.CollValue[storagev1.Params](cdc),
		),
	}
	schema, err := sb.Build()
	if err != nil {
		panic(err)
	}
	k.Schema = schema

	return k
}

// GetAuthority returns the module authority
func (k Keeper) GetAuthority() string {
	return k.authority
}

// GetParams returns the current module parameters
func (k Keeper) GetParams(ctx context.Context) (params storagev1.Params) {
	params, err := k.params.Get(ctx)
	if err != nil {
		// If params don't exist, return defaults
		k.Logger(sdk.UnwrapSDKContext(ctx)).Error("GetParams: failed to load params; returning defaults", "err", err)
		return storagev1.DefaultParams()
	}
	return params
}

// SetParams sets the module parameters
func (k Keeper) SetParams(ctx context.Context, params storagev1.Params) error {
	if err := params.Validate(); err != nil {
		return err
	}
	return k.params.Set(ctx, params)
}

// Logger returns a module-specific logger
func (k Keeper) Logger(ctx sdk.Context) log.Logger {
	return ctx.Logger().With("module", "x/storage")
}

// GetStorageMetrics returns the storage metrics for a given owner address
func (k Keeper) GetStorageMetrics(ctx context.Context, owner string) (storagev1.StorageMetrics, error) {
	metrics, err := k.StorageMetricsMap.Get(ctx, owner)
	if err != nil {
		if errors.IsOf(err, collections.ErrNotFound) {
			// Return zero metrics if not found - calculate MinStakeAmount for zero bytes
			minStakeAmount, calcErr := k.CalculateMinStakeAmount(ctx, 0)
			if calcErr != nil {
				return storagev1.StorageMetrics{}, calcErr
			}
			return storagev1.StorageMetrics{
				Owner:          owner,
				TotalBytes:     0,
				MinStakeAmount: minStakeAmount,
			}, nil
		}
		return storagev1.StorageMetrics{}, err
	}
	return metrics, nil
}

// UpdateStorageMetrics updates the storage metrics for a given owner by a byte delta
func (k Keeper) UpdateStorageMetrics(ctx context.Context, owner string, byteDelta int64) error {
	// Get current metrics
	metrics, err := k.GetStorageMetrics(ctx, owner)
	if err != nil {
		return err
	}

	// Calculate new total bytes, ensuring it doesn't go below zero
	newTotalBytes := int64(metrics.TotalBytes) + byteDelta
	if newTotalBytes < 0 {
		newTotalBytes = 0
	}

	// Update metrics
	metrics.TotalBytes = uint64(newTotalBytes)

	// Calculate new MinStakeAmount
	minStakeAmount, err := k.CalculateMinStakeAmount(ctx, metrics.TotalBytes)
	if err != nil {
		return err
	}
	metrics.MinStakeAmount = minStakeAmount

	// Save updated metrics
	return k.StorageMetricsMap.Set(ctx, owner, metrics)
}

// CalculateMinStakeAmount calculates the minimum stake amount required for the given number of bytes
func (k Keeper) CalculateMinStakeAmount(ctx context.Context, totalBytes uint64) (string, error) {
	// Get current parameters
	params := k.GetParams(ctx)

	// Parse the storage_stake_multiple as a decimal
	stakeMultiple, err := math.LegacyNewDecFromStr(params.StorageStakeMultiple)
	if err != nil {
		return "", errors.Wrap(err, "failed to parse storage_stake_multiple")
	}

	// Convert totalBytes to decimal for calculation
	bytesDecimal := math.LegacyNewDecFromInt(math.NewIntFromUint64(totalBytes))

	// Calculate: totalBytes × storage_stake_multiple
	minStakeDecimal := bytesDecimal.Mul(stakeMultiple)

	// Truncate to integer (removing fractional part) and return as string
	minStakeInt := minStakeDecimal.TruncateInt()
	return minStakeInt.String(), nil
}

// GetTotalDelegatedStake returns the total amount a delegator has bonded across all validators
func (k Keeper) GetTotalDelegatedStake(ctx context.Context, delegatorAddr string) (math.Int, error) {
	// Parse the delegator address
	delAddr, err := sdk.AccAddressFromBech32(delegatorAddr)
	if err != nil {
		return math.ZeroInt(), errors.Wrap(err, "failed to parse delegator address")
	}

	// Query the total bonded amount using the staking keeper
	totalBonded, err := k.stakingKeeper.GetDelegatorBonded(ctx, delAddr)
	if err != nil {
		return math.ZeroInt(), errors.Wrap(err, "failed to get total bonded amount")
	}

	return totalBonded, nil
}
