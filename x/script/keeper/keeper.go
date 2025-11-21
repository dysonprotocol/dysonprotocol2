package keeper

import (
	"context"

	"cosmossdk.io/collections"
	"cosmossdk.io/core/address"
	"cosmossdk.io/core/store"
	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"
	scripttypes "dysonprotocol.com/x/script/types"

	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"
	authzkeeper "github.com/cosmos/cosmos-sdk/x/authz/keeper"
)

var (
	ScriptMapPrefix = collections.NewPrefix(0)
	ParamsKey       = collections.NewPrefix(1)
)

// Ensure the keeper types implement required interfaces
var _ scripttypes.BranchKeeper = (*BranchService)(nil)

// BranchService implements the atomic execution functionality
type BranchService struct {
	sdkCtx sdk.Context
}

// ExecuteWithGasLimit runs a function with a specific gas limit and returns gas used and a write func
func (bs *BranchService) ExecuteWithGasLimit(ctx context.Context, gasLimit uint64, fn func(ctx context.Context) error) (uint64, func(), error) {
	// Create a cached context with a gas meter with the specified limit
	sdkCtx := bs.sdkCtx.WithGasMeter(storetypes.NewGasMeter(gasLimit))

	// Create a cache-wrapped context that creates an isolated context for the execution
	cacheCtx, write := sdkCtx.CacheContext()

	// Convert the SDK context to a generic context
	fnCtx := sdk.WrapSDKContext(cacheCtx)

	// Track the gas consumed before execution
	gasConsumedBefore := sdkCtx.GasMeter().GasConsumed()

	// Execute the function
	err := fn(fnCtx)

	// Calculate the amount of gas consumed during execution
	gasUsed := cacheCtx.GasMeter().GasConsumed() - gasConsumedBefore

	return gasUsed, write, err
}

type Keeper struct {
	// Core services
	App            *baseapp.BaseApp
	addressCodec   address.Codec
	validatorCodec address.Codec
	cdc            codec.Codec
	Schema         collections.Schema

	// Store service
	KVStoreService store.KVStoreService

	// Collections
	ScriptMap collections.Map[string, scripttypes.Script]
	params    collections.Item[scripttypes.Params]

	// Authority for governance operations
	authority string

	// Optional nameservice keeper for resolving names to addresses
	NameserviceKeeper scripttypes.NameserviceKeeper

	// Account keeper for accessing account information
	AccountKeeper scripttypes.AccountKeeper

	// Authz keeper for managing authorizations
	AuthzKeeper authzkeeper.Keeper

	// Service interfaces
	MsgRouterService   *baseapp.MsgServiceRouter
	QueryRouterService *baseapp.GRPCQueryRouter
}

// MsgRequest defines a request to dispatch a message

// NewKeeper creates a new script keeper.
func NewKeeper(
	app *baseapp.BaseApp,
	kvStoreService store.KVStoreService,
	cdc codec.Codec,
	accKeeper scripttypes.AccountKeeper,
	nameserviceKeeper scripttypes.NameserviceKeeper,
	authzKeeper authzkeeper.Keeper,
	addressCodec address.Codec,
	validatorCodec address.Codec,
	msgServiceRouter *baseapp.MsgServiceRouter,
	queryServiceRouter *baseapp.GRPCQueryRouter,
	authority string,
) Keeper {
	sb := collections.NewSchemaBuilder(kvStoreService)

	k := Keeper{
		App:                app,
		cdc:                cdc,
		addressCodec:       addressCodec,
		validatorCodec:     validatorCodec,
		KVStoreService:     kvStoreService,
		NameserviceKeeper:  nameserviceKeeper,
		AccountKeeper:      accKeeper,
		AuthzKeeper:        authzKeeper,
		ScriptMap:          collections.NewMap(sb, ScriptMapPrefix, "script_map", collections.StringKey, codec.CollValue[scripttypes.Script](cdc)),
		params:             collections.NewItem(sb, ParamsKey, "params", codec.CollValue[scripttypes.Params](cdc)),
		MsgRouterService:   msgServiceRouter,
		QueryRouterService: queryServiceRouter,
		authority:          authority,
	}

	schema, err := sb.Build()
	if err != nil {
		panic(err)
	}
	k.Schema = schema
	return k
}

// Logger returns a module-specific logger
func (k Keeper) Logger(ctx sdk.Context) log.Logger {
	return ctx.Logger().With("module", "x/script")
}
