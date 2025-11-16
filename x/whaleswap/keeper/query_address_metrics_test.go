package keeper

import (
	"testing"

	"cosmossdk.io/collections"
	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/runtime"
	"github.com/cosmos/cosmos-sdk/testutil"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"github.com/stretchr/testify/require"

	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

func TestAddressMetrics_NilAndInvalidRequests(t *testing.T) {
	t.Parallel()
	k, ctx := newMetricsKeeper(t)

	// Test with nil request
	_, err := k.AddressMetrics(ctx, nil)
	require.Error(t, err)
	require.Contains(t, err.Error(), "address required")

	// Test with empty address
	req := &whaleswapv1.QueryAddressMetricsRequest{
		Address: "",
	}
	_, err = k.AddressMetrics(ctx, req)
	require.Error(t, err)
	require.Contains(t, err.Error(), "address required")

	// Test with invalid address
	req = &whaleswapv1.QueryAddressMetricsRequest{
		Address: "invalid",
	}
	_, err = k.AddressMetrics(ctx, req)
	require.Error(t, err)
	require.Contains(t, err.Error(), "invalid address")
}

func TestAddressMetricsAll_NilRequest(t *testing.T) {
	t.Parallel()
	k, ctx := newMetricsKeeper(t)

	resp, err := k.AddressMetricsAll(ctx, nil)
	require.NoError(t, err)
	require.NotNil(t, resp)
	require.Empty(t, resp.Metrics)
}

func TestAddressMetricsAll_Pagination(t *testing.T) {
	t.Parallel()
	k, ctx := newMetricsKeeper(t)

	records := []whaleswapv1.AddressMetrics{
		{Address: "addr1", BlockHeight: 1},
		{Address: "addr2", BlockHeight: 2},
	}
	for _, rec := range records {
		require.NoError(t, k.AddressMetricsMap.Set(ctx, rec.Address, rec))
	}

	resp, err := k.AddressMetricsAll(ctx, &whaleswapv1.QueryAddressMetricsAllRequest{
		Pagination: &query.PageRequest{Limit: 1},
	})
	require.NoError(t, err)
	require.Len(t, resp.Metrics, 1)
	require.Equal(t, "addr1", resp.Metrics[0].Address)
	require.NotNil(t, resp.Pagination)
	require.NotEmpty(t, resp.Pagination.NextKey)

	resp, err = k.AddressMetricsAll(ctx, &whaleswapv1.QueryAddressMetricsAllRequest{
		Pagination: &query.PageRequest{Key: resp.Pagination.NextKey, Limit: 1},
	})
	require.NoError(t, err)
	require.Len(t, resp.Metrics, 1)
	require.Equal(t, "addr2", resp.Metrics[0].Address)
}

// NOTE: Full integration test for AddressMetrics with actual state
// should be added to the integration test suite where proper keeper
// initialization with bank, nameservice, and other dependencies exists.
// This test file only validates nil/empty request handling which doesn't
// require a full keeper setup.

func newMetricsKeeper(t *testing.T) (Keeper, sdk.Context) {
	t.Helper()

	storeKey := storetypes.NewKVStoreKey(whaleswap.StoreKey)
	memKey := storetypes.NewTransientStoreKey("transient_whaleswap")
	testCtx := testutil.DefaultContextWithDB(t, storeKey, memKey)

	storeService := runtime.NewKVStoreService(storeKey)
	ir := codectypes.NewInterfaceRegistry()
	cdc := codec.NewProtoCodec(ir)

	k := Keeper{
		cdc:    cdc,
		store:  storeService,
		logger: log.NewNopLogger(),
	}

	sb := collections.NewSchemaBuilder(storeService)
	k.AddressMetricsMap = collections.NewMap(
		sb,
		AddressMetricsPrefix,
		"address_metrics",
		collections.StringKey,
		codec.CollValue[whaleswapv1.AddressMetrics](cdc),
	)

	schema, err := sb.Build()
	require.NoError(t, err)
	k.Schema = schema

	return k, testCtx.Ctx
}
