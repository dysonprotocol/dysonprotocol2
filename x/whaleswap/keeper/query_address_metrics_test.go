package keeper

import (
	"testing"

	"github.com/stretchr/testify/require"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

func TestAddressMetrics_NilAndInvalidRequests(t *testing.T) {
	t.Parallel()
	k, ctx := newTestKeeper(t)

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

// NOTE: Full integration test for AddressMetrics with actual state
// should be added to the integration test suite where proper keeper
// initialization with bank, nameservice, and other dependencies exists.
// This test file only validates nil/empty request handling which doesn't
// require a full keeper setup.
