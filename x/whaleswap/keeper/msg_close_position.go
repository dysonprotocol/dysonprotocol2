package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ClosePosition closes an open leveraged position and settles collateral/profit.
func (k Keeper) ClosePosition(ctx context.Context, msg *whaleswapv1.MsgClosePosition) (*whaleswapv1.MsgClosePositionResponse, error) {
	if msg == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "message cannot be nil")
	}
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	// Check for invalid position data before ownership to avoid panics
	if pos.BorrowTime == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid position: missing borrow_time")
	}
	// Ownership check must return before any further logic to avoid side effects or nil derefs
	if pos.User != msg.User {
		// Use a stable message that includes the substring expected by tests
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "unauthorized: not position owner")
	}
	if !k.CanCloseBefore(ctx, &pos) {
		blocks := k.BlocksUntilCloseable(ctx, &pos)
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrBlockDelayNotPassed, "position locked for %d more blocks", blocks)
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate interest
	rate, err := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	if err != nil {
		return nil, err
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, err := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	if err != nil {
		return nil, err
	}

	// Return collateral and profit to user; pool receives repayment
	userAddr, err := k.addr(ctx, msg.User)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	// Swap held back to borrowed denom via MakeTrade using the borrow vault as trader
	borrowVault := k.leverageBorrowVaultBech(ctx)
	mt := &whaleswapv1.MsgMakeTrade{
		Trader:    borrowVault,
		MaxInput:  sdk.NewCoins(pos.Held),
		MinOutput: sdk.NewCoins(),
		Operations: []whaleswapv1.TradeOperation{
			{Op: &whaleswapv1.TradeOperation_Swap{Swap: &whaleswapv1.SwapLeg{PoolId: pos.PoolId, SwapIn: pos.Held}}},
		},
		Note: "leverage-close",
	}
	mtResp, mtErr := k.MakeTrade(ctx, mt)
	if mtErr != nil {
		return nil, cosmossdkerrors.Wrap(mtErr, "failed leverage close MakeTrade")
	}
	proceedsBorrow := mtResp.TraderOutputs.AmountOf(pos.Borrowed.Denom)
	if !proceedsBorrow.IsPositive() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "close swap produced no %s output", pos.Borrowed.Denom)
	}
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)

	// Determine funds available to cover repayment (after all swaps and fees)
	var collateralUsedAmount math.Int
	var collateralSwapped bool
	var totalProceedsFromSwaps math.Int // Total funds in vault (for cross-denom case)
	var profit sdk.Coin

	if proceedsBorrow.GTE(repayment) {
		// Profitable: proceeds alone cover full repayment
		// User gets: all collateral back + profit from proceeds
		collateralUsedAmount = math.ZeroInt()
		collateralSwapped = false
		totalProceedsFromSwaps = proceedsBorrow
		pnl := proceedsBorrow.Sub(repayment)
		profit = sdk.NewCoin(pos.Borrowed.Denom, pnl)
	} else {
		// Underwater: proceeds insufficient, need to use collateral
		// User gets: remaining collateral (if any), NO profit
		shortfall := repayment.Sub(proceedsBorrow)

		if pos.Collateral.Denom == pos.Borrowed.Denom {
			// Same denom: collateral can directly cover shortfall
			if pos.Collateral.Amount.LT(shortfall) {
				// Insufficient: reject transaction to prevent pool loss
				return nil, cosmossdkerrors.Wrapf(
					whaleswapv1.ErrInsufficientCollateral,
					"position underwater: proceeds=%s + collateral=%s < repayment=%s (shortfall=%s)",
					proceedsBorrow,
					pos.Collateral.Amount,
					repayment,
					shortfall,
				)
			}
			// Collateral covers shortfall
			collateralUsedAmount = shortfall
			collateralSwapped = false
			totalProceedsFromSwaps = proceedsBorrow
			profit = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
		} else {
			// Cross-denom collateral: must swap to borrowed denom
			collateralToSwap := pos.Collateral

			// Zero out position collateral and persist BEFORE moving funds
			pos.Collateral.Amount = math.ZeroInt()
			if err := k.LeveragePositions.Set(ctx, msg.PositionId, pos); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to update position before collateral swap")
			}

			// Move collateral from module → borrow vault for swap
			if err := k.moveModuleToModule(ctx, whaleswap.ModuleName, whaleswap.LeverageBorrowVaultModuleName, sdk.NewCoins(collateralToSwap)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to move collateral to borrow vault for swap")
			}

			// Swap collateral to borrowed denom
			collateralSwapMt := &whaleswapv1.MsgMakeTrade{
				Trader:    borrowVault,
				MaxInput:  sdk.NewCoins(collateralToSwap),
				MinOutput: sdk.NewCoins(),
				Operations: []whaleswapv1.TradeOperation{
					{Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{
							PoolId: pos.PoolId,
							SwapIn: collateralToSwap,
						},
					}},
				},
				Note: "leverage-close-collateral-swap",
			}
			collSwapResp, collSwapErr := k.MakeTrade(ctx, collateralSwapMt)
			if collSwapErr != nil {
				return nil, cosmossdkerrors.Wrap(collSwapErr, "failed to swap collateral for shortfall coverage")
			}

			collateralProceeds := collSwapResp.TraderOutputs.AmountOf(pos.Borrowed.Denom)
			if !collateralProceeds.IsPositive() {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "collateral swap produced no %s output", pos.Borrowed.Denom)
			}

			totalProceedsFromSwaps = proceedsBorrow.Add(collateralProceeds)

			// Critical check: reject if still underwater after swapping collateral
			if totalProceedsFromSwaps.LT(repayment) {
				return nil, cosmossdkerrors.Wrapf(
					whaleswapv1.ErrInsufficientCollateral,
					"position underwater after collateral swap: held_proceeds=%s + collateral_proceeds=%s < repayment=%s",
					proceedsBorrow,
					collateralProceeds,
					repayment,
				)
			}

			// Collateral was entirely swapped
			collateralUsedAmount = collateralToSwap.Amount
			collateralSwapped = true
			// Calculate profit from total proceeds (may be positive if collateral swap yielded excess)
			pnl := totalProceedsFromSwaps.Sub(repayment)
			profit = sdk.NewCoin(pos.Borrowed.Denom, pnl)

			sdkCtx.Logger().Info("ClosePosition: cross-denom collateral swap executed",
				"held_proceeds", proceedsBorrow,
				"collateral_swapped", collateralToSwap.Amount,
				"collateral_proceeds", collateralProceeds,
				"total_proceeds", totalProceedsFromSwaps,
				"repayment", repayment,
				"profit", pnl)
		}
	}

	// Reload pool to get current state after MakeTrade(s)
	pool, err = k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to reload pool %d", pos.PoolId)
	}

	// Move swap proceeds from borrow vault to module and restore pool reserves
	// Important: funds must be in module BEFORE we add to pool.Coins for invariants
	if collateralSwapped {
		// Cross-denom case: both swaps executed in vault
		// Move all proceeds (held swap + collateral swap) to module
		proceedsCoin := sdk.NewCoin(pos.Borrowed.Denom, totalProceedsFromSwaps)
		if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(proceedsCoin)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to transfer proceeds to module")
		}

		// Restore pool reserves with full repayment (all funds now in module)
		repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, repayment)
		pool.Coins = pool.Coins.Add(repaymentCoin)
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
		}

		// Return profit to user (excess over repayment, if any)
		if profit.Amount.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
			}
		}
	} else {
		// Same-denom case: swap proceeds in vault, collateral (if needed) already in module
		// Move swap proceeds from vault to module
		proceedsCoin := sdk.NewCoin(pos.Borrowed.Denom, totalProceedsFromSwaps)
		if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(proceedsCoin)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to transfer proceeds to module")
		}

		// Restore pool reserves with full repayment
		// repayment funded by: totalProceedsFromSwaps (just moved to module) + collateralUsedAmount (already in module)
		repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, repayment)
		pool.Coins = pool.Coins.Add(repaymentCoin)
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
		}

		// Return remaining collateral to user (amount not used for repayment)
		remainingCollateral := pos.Collateral.Amount.Sub(collateralUsedAmount)
		if remainingCollateral.IsPositive() {
			remainingCoin := sdk.NewCoin(pos.Collateral.Denom, remainingCollateral)
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(remainingCoin)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
			}
		}

		// Return profit to user (only possible if proceeds >= repayment, meaning collateralUsedAmount = 0)
		if profit.Amount.IsPositive() {
			if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
			}
		}
	}

	// Update pool accounting: decrease total_borrowed and add interest earned
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
	pool.TotalBorrowed = totalBorrowed
	interestEarned := sdk.NewCoins(pool.InterestEarned...).Add(sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt()))
	pool.InterestEarned = interestEarned
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Delete position
	if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
	}

	// Emit event
	interestCoin := sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt())
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionClosed{
		PositionId:      msg.PositionId,
		User:            msg.User,
		PoolId:          pos.PoolId,
		Profit:          profit,
		AccruedInterest: interestCoin,
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	// Invariants after settlement
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after ClosePosition")
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after ClosePosition")
	}

	return &whaleswapv1.MsgClosePositionResponse{
		Profit:          profit,
		AccruedInterest: interestCoin,
	}, nil
}
