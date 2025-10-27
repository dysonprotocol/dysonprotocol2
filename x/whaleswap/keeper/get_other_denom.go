package keeper

import (
	"fmt"

	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// getOtherDenom returns the other denomination in a two-coin pool.
// It does not rely on array position semantics; instead it explicitly
// checks both denoms and returns the one that doesn't match knownDenom.
func (k Keeper) getOtherDenom(pool *whaleswapv1.Pool, knownDenom string) (string, error) {
	if len(pool.Coins) != 2 {
		return "", fmt.Errorf("pool must have exactly 2 denoms, got %d", len(pool.Coins))
	}
	if pool.Coins[0].Denom == knownDenom {
		return pool.Coins[1].Denom, nil
	}
	if pool.Coins[1].Denom == knownDenom {
		return pool.Coins[0].Denom, nil
	}
	return "", fmt.Errorf("denom %s not in pool", knownDenom)
}
