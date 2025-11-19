package cli

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	smath "cosmossdk.io/math"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/client/tx"
	sdk "github.com/cosmos/cosmos-sdk/types"

	whaleswaptypes "dysonprotocol.com/x/whaleswap/types"
)

// CmdTakeOffer provides a custom CLI for taking one or more offers using a repeatable
// string array flag. Each occurrence encodes a single TakeItem in a simple key=value format.

func parseUintOrPanic(s string) uint64 {
	// Minimal, strict parse; we bubble errors as clear CLI messages above; this is defensive
	var u uint64
	for _, ch := range s {
		if ch < '0' || ch > '9' {
			panic(fmt.Errorf("invalid unsigned integer: %s", s))
		}
	}
	// Fast path since we validated digits only
	for i := 0; i < len(s); i++ {
		u = u*10 + uint64(s[i]-'0')
	}
	return u
}

// --- Custom commands to handle repeated flags that must map to arrays ---

func parseCoinList(name string, vals []string) ([]sdk.Coin, error) {
	coins := sdk.NewCoins()
	for _, v := range vals {
		c, err := sdk.ParseCoinNormalized(strings.TrimSpace(v))
		if err != nil {
			return nil, fmt.Errorf("invalid %s coin '%s': %w", name, v, err)
		}
		coins = coins.Add(c)
	}
	return coins, nil
}

// CmdCreatePool provides custom parsing for repeated --coins flags.
func CmdCreatePool() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "create-pool",
		Short: "Create a new AMM pool",
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientTxContext(cmd)
			if err != nil {
				return err
			}
			coinsFlags, err := cmd.Flags().GetStringArray("coins")
			if err != nil {
				return fmt.Errorf("failed to read --coins flags: %w", err)
			}
			if len(coinsFlags) != 2 {
				return fmt.Errorf("exactly two --coins flags are required (one coin per flag)")
			}
			coinList, err := parseCoinList("coins", coinsFlags)
			if err != nil {
				return err
			}
			feeRateFlags, err := cmd.Flags().GetStringArray("fee-rate")
			if err != nil {
				return fmt.Errorf("failed to read --fee-rate: %w", err)
			}

			// Denoms in canonical pool order (coinList is sanitized/sorted)
			denom1, denom2 := coinList[0].Denom, coinList[1].Denom

			// Per-denom risk ratios
			mcrFlags, err := cmd.Flags().GetStringArray("min-collateral-ratio")
			if err != nil {
				return fmt.Errorf("failed to read --min-collateral-ratio: %w", err)
			}
			if len(mcrFlags) == 0 {
				return fmt.Errorf("--min-collateral-ratio is required (1 or 2 values)")
			}
			var minCollateralRatio sdk.DecCoins
			switch len(mcrFlags) {
			case 1:
				d := mustDec(strings.TrimSpace(mcrFlags[0]))
				minCollateralRatio = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(denom1, d),
					sdk.NewDecCoinFromDec(denom2, d),
				)
			case 2:
				if parsed, ok := tryParseDecCoins(mcrFlags); ok {
					minCollateralRatio = parsed
				} else {
					d1 := mustDec(strings.TrimSpace(mcrFlags[0]))
					d2 := mustDec(strings.TrimSpace(mcrFlags[1]))
					minCollateralRatio = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(denom1, d1),
						sdk.NewDecCoinFromDec(denom2, d2),
					)
				}
			default:
				return fmt.Errorf("--min-collateral-ratio accepts 1 or 2 values")
			}
			irFlags, err := cmd.Flags().GetStringArray("interest-rate")
			if err != nil {
				return fmt.Errorf("failed to read --interest-rate flags: %w", err)
			}
			var interestRate sdk.DecCoins
			switch len(irFlags) {
			case 0:
				// Send empty; server normalizes to two entries
				interestRate = sdk.NewDecCoins()
			case 1:
				dc, perr := sdk.ParseDecCoin(strings.TrimSpace(irFlags[0]))
				if perr != nil {
					return fmt.Errorf("invalid --interest-rate '%s': %w", irFlags[0], perr)
				}
				interestRate = sdk.NewDecCoins(dc)
			case 2:
				parsed := make([]sdk.DecCoin, 0, 2)
				for _, v := range irFlags {
					dc, perr := sdk.ParseDecCoin(strings.TrimSpace(v))
					if perr != nil {
						return fmt.Errorf("invalid --interest-rate '%s': %w", v, perr)
					}
					parsed = append(parsed, dc)
				}
				interestRate = sdk.NewDecCoins(parsed...)
			default:
				return fmt.Errorf("--interest-rate must be provided 0, 1, or 2 times (APR per denom as DecCoin)")
			}

			mbpFlags, err := cmd.Flags().GetStringArray("max-borrow-percent")
			if err != nil {
				return fmt.Errorf("failed to read --max-borrow-percent flags: %w", err)
			}
			var maxBorrowPercent sdk.DecCoins
			switch len(mbpFlags) {
			case 0:
				// Default both to 0.80
				d := mustDec("0.80")
				maxBorrowPercent = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(coinList[0].Denom, d),
					sdk.NewDecCoinFromDec(coinList[1].Denom, d),
				)
			case 1:
				// Single decimal applies to both denoms
				d := mustDec(strings.TrimSpace(mbpFlags[0]))
				maxBorrowPercent = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(coinList[0].Denom, d),
					sdk.NewDecCoinFromDec(coinList[1].Denom, d),
				)
			case 2:
				// Try parsing as DecCoin first; fallback to decimals mapped to denoms
				parsed, ok := tryParseDecCoins(mbpFlags)
				if ok {
					maxBorrowPercent = parsed
				} else {
					d1 := mustDec(strings.TrimSpace(mbpFlags[0]))
					d2 := mustDec(strings.TrimSpace(mbpFlags[1]))
					maxBorrowPercent = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(coinList[0].Denom, d1),
						sdk.NewDecCoinFromDec(coinList[1].Denom, d2),
					)
				}
			default:
				return fmt.Errorf("--max-borrow-percent accepts 0, 1, or 2 values")
			}

			// liquidation-threshold (1 or 2 values; default 1.2 if omitted)
			liqFlags, err := cmd.Flags().GetStringArray("liquidation-threshold")
			if err != nil {
				return fmt.Errorf("failed to read --liquidation-threshold: %w", err)
			}
			var liquidationThreshold sdk.DecCoins
			switch len(liqFlags) {
			case 0:
				d := mustDec("1.2")
				liquidationThreshold = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(denom1, d),
					sdk.NewDecCoinFromDec(denom2, d),
				)
			case 1:
				d := mustDec(strings.TrimSpace(liqFlags[0]))
				liquidationThreshold = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(denom1, d),
					sdk.NewDecCoinFromDec(denom2, d),
				)
			case 2:
				if parsed, ok := tryParseDecCoins(liqFlags); ok {
					liquidationThreshold = parsed
				} else {
					d1 := mustDec(strings.TrimSpace(liqFlags[0]))
					d2 := mustDec(strings.TrimSpace(liqFlags[1]))
					liquidationThreshold = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(denom1, d1),
						sdk.NewDecCoinFromDec(denom2, d2),
					)
				}
			default:
				return fmt.Errorf("--liquidation-threshold accepts 0, 1, or 2 values")
			}

			// fee-rate: 0, 1, or 2 flags as DecCoins; 0 => defaults to 0 for both denoms
			var feeRate sdk.DecCoins
			switch len(feeRateFlags) {
			case 0:
				// default to zero rates
				feeRate = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(coinList[0].Denom, mustDec("0")),
					sdk.NewDecCoinFromDec(coinList[1].Denom, mustDec("0")),
				)
			case 1:
				dc, perr := sdk.ParseDecCoin(strings.TrimSpace(feeRateFlags[0]))
				if perr != nil {
					return fmt.Errorf("invalid --fee-rate '%s': %w", feeRateFlags[0], perr)
				}
				feeRate = sdk.NewDecCoins(dc)
			case 2:
				parsed := make([]sdk.DecCoin, 0, 2)
				for _, v := range feeRateFlags {
					dc, perr := sdk.ParseDecCoin(strings.TrimSpace(v))
					if perr != nil {
						return fmt.Errorf("invalid --fee-rate '%s': %w", v, perr)
					}
					parsed = append(parsed, dc)
				}
				feeRate = sdk.NewDecCoins(parsed...)
			default:
				return fmt.Errorf("--fee-rate must be provided 0, 1, or 2 times (per-denom fee as DecCoin)")
			}

			boundFlags, err := cmd.Flags().GetStringArray("bound-percent")
			if err != nil {
				return fmt.Errorf("failed to read --bound-percent: %w", err)
			}
			var boundPercent sdk.DecCoins
			switch len(boundFlags) {
			case 0:
				// leave empty to skip update
			case 2:
				if parsed, ok := tryParseDecCoins(boundFlags); ok {
					if len(parsed) != 2 || parsed[0].Denom != denom1 || parsed[1].Denom != denom2 {
						return fmt.Errorf("--bound-percent DecCoins must match pool denoms in canonical order (%s,%s)", denom1, denom2)
					}
					zero := smath.LegacyZeroDec()
					oneDec := smath.LegacyNewDec(1)
					for _, dc := range parsed {
						if !dc.Amount.GT(zero) || dc.Amount.GT(oneDec) {
							return fmt.Errorf("--bound-percent amounts must satisfy 0 < x <= 1; invalid entry for %s", dc.Denom)
						}
					}
					boundPercent = parsed
				} else {
					b1 := mustDec(strings.TrimSpace(boundFlags[0]))
					b2 := mustDec(strings.TrimSpace(boundFlags[1]))
					zero := smath.LegacyZeroDec()
					oneDec := smath.LegacyNewDec(1)
					if !b1.GT(zero) || b1.GT(oneDec) {
						return fmt.Errorf("--bound-percent value for %s must satisfy 0 < x <= 1", denom1)
					}
					if !b2.GT(zero) || b2.GT(oneDec) {
						return fmt.Errorf("--bound-percent value for %s must satisfy 0 < x <= 1", denom2)
					}
					boundPercent = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(denom1, b1),
						sdk.NewDecCoinFromDec(denom2, b2),
					)
				}
			default:
				return fmt.Errorf("--bound-percent accepts exactly two values (one per denom) or omit entirely for defaults")
			}

			msg := &whaleswaptypes.MsgCreatePool{
				Creator:                   clientCtx.GetFromAddress().String(),
				Coins:                     coinList,
				FeeRate:                   feeRate,
				MinInitialCollateralRatio: minCollateralRatio,
				InterestRate:              interestRate,
				MaxBorrowPercent:          maxBorrowPercent,
				LiquidationThreshold:      liquidationThreshold,
				BoundPercent:              boundPercent,
			}
			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}
	cmd.Flags().StringArray("coins", nil, "Repeatable; provide exactly two flags, one per coin (e.g., 1000udys)")
	cmd.Flags().StringArray("fee-rate", nil, "Repeatable (0, 1, or 2); per-denom swap fee as DecCoin in [0,1) (e.g., 0.003udys)")
	cmd.Flags().StringArray("min-collateral-ratio", nil, "Repeatable (1 or 2); min collateral ratio per denom as Dec or DecCoin (e.g., 1.5 or 1.5udys)")
	cmd.Flags().StringArray("interest-rate", nil, "Repeatable (0, 1, or 2); APR per denom as DecCoin (e.g., 0.10udys). Optional; defaults to 0 for missing denoms")
	cmd.Flags().StringArray("liquidation-threshold", nil, "Repeatable (0, 1, or 2); liquidation threshold per denom as Dec or DecCoin (default 1.2)")
	cmd.Flags().StringArray("max-borrow-percent", nil, "Repeatable; 0, 1, or 2 values. If decimals without denoms are given, they map to the two pool denoms (e.g., 0.80)")
	cmd.Flags().StringArray("bound-percent", nil, "Repeatable (optional); provide two decimals or DecCoins specifying max fractional price drop per sold denom (0 < x <= 1). Omit for unbounded")
	flags.AddTxFlagsToCmd(cmd)
	return cmd
}

// CmdUpdatePoolConfig updates dynamic pool parameters.
func CmdUpdatePoolConfig() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "update-pool-config",
		Short: "Update pool dynamic configuration",
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientTxContext(cmd)
			if err != nil {
				return err
			}
			poolID, err := cmd.Flags().GetUint64("pool-id")
			if err != nil {
				return err
			}
			feeRateFlags, err := cmd.Flags().GetStringArray("fee-rate")
			if err != nil {
				return fmt.Errorf("failed to read --fee-rate: %w", err)
			}

			// Load current pool for defaults/denoms
			q := whaleswaptypes.NewQueryClient(clientCtx)
			poolResp, qerr := q.Pool(cmd.Context(), &whaleswaptypes.QueryPoolRequest{PoolId: poolID})
			if qerr != nil {
				return fmt.Errorf("failed to query pool %d: %w", poolID, qerr)
			}
			pool := poolResp.Pool

			// Interest rate: 0, 1, or 2 flags (same as create-pool). 0 => keep current; 1/2 => parse.
			irFlags, err := cmd.Flags().GetStringArray("interest-rate")
			if err != nil {
				return fmt.Errorf("failed to read --interest-rate flags: %w", err)
			}
			var interestRate sdk.DecCoins
			switch len(irFlags) {
			case 0:
				interestRate = sdk.NewDecCoins(pool.InterestRate...)
			case 1:
				dc, perr := sdk.ParseDecCoin(strings.TrimSpace(irFlags[0]))
				if perr != nil {
					return fmt.Errorf("invalid --interest-rate '%s': %w", irFlags[0], perr)
				}
				interestRate = sdk.NewDecCoins(dc)
			case 2:
				parsed := make([]sdk.DecCoin, 0, 2)
				for _, v := range irFlags {
					dc, perr := sdk.ParseDecCoin(strings.TrimSpace(v))
					if perr != nil {
						return fmt.Errorf("invalid --interest-rate '%s': %w", v, perr)
					}
					parsed = append(parsed, dc)
				}
				interestRate = sdk.NewDecCoins(parsed...)
			default:
				return fmt.Errorf("--interest-rate must be provided 0, 1, or 2 times (APR per denom as DecCoin)")
			}

			// Max borrow percent: optional; fallback to current pool if not provided
			var maxBorrowPercent sdk.DecCoins
			mbpFlags, err := cmd.Flags().GetStringArray("max-borrow-percent")
			if err != nil {
				return fmt.Errorf("failed to read --max-borrow-percent flags: %w", err)
			}
			if len(mbpFlags) == 2 {
				parsed2 := make([]sdk.DecCoin, 0, 2)
				for _, v := range mbpFlags {
					dc, perr := sdk.ParseDecCoin(strings.TrimSpace(v))
					if perr != nil {
						return fmt.Errorf("invalid --max-borrow-percent '%s': %w", v, perr)
					}
					parsed2 = append(parsed2, dc)
				}
				maxBorrowPercent = sdk.NewDecCoins(parsed2...)
			} else {
				maxBorrowPercent = sdk.NewDecCoins(pool.MaxBorrowPercent...)
			}

			// Denoms in canonical order from current pool
			denom1, denom2 := pool.Coins[0].Denom, pool.Coins[1].Denom

			// liquidation-threshold: allow override or fallback to current pool value (0,1,2)
			liqFlags, _ := cmd.Flags().GetStringArray("liquidation-threshold")
			var liquidationThreshold sdk.DecCoins
			switch len(liqFlags) {
			case 0:
				liquidationThreshold = sdk.NewDecCoins(pool.LiquidationThreshold...)
			case 1:
				d := mustDec(strings.TrimSpace(liqFlags[0]))
				liquidationThreshold = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(denom1, d),
					sdk.NewDecCoinFromDec(denom2, d),
				)
			case 2:
				if parsed, ok := tryParseDecCoins(liqFlags); ok {
					liquidationThreshold = parsed
				} else {
					d1 := mustDec(strings.TrimSpace(liqFlags[0]))
					d2 := mustDec(strings.TrimSpace(liqFlags[1]))
					liquidationThreshold = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(denom1, d1),
						sdk.NewDecCoinFromDec(denom2, d2),
					)
				}
			default:
				return fmt.Errorf("--liquidation-threshold accepts 0, 1, or 2 values")
			}

			// min collateral ratio: allow override or fallback to current pool values
			mcrFlags, _ := cmd.Flags().GetStringArray("min-collateral-ratio")
			var minCollateralRatio sdk.DecCoins
			switch len(mcrFlags) {
			case 0:
				minCollateralRatio = sdk.NewDecCoins(pool.MinInitialCollateralRatio...)
			case 1:
				d := mustDec(strings.TrimSpace(mcrFlags[0]))
				minCollateralRatio = sdk.NewDecCoins(
					sdk.NewDecCoinFromDec(denom1, d),
					sdk.NewDecCoinFromDec(denom2, d),
				)
			case 2:
				if parsed, ok := tryParseDecCoins(mcrFlags); ok {
					minCollateralRatio = parsed
				} else {
					d1 := mustDec(strings.TrimSpace(mcrFlags[0]))
					d2 := mustDec(strings.TrimSpace(mcrFlags[1]))
					minCollateralRatio = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(denom1, d1),
						sdk.NewDecCoinFromDec(denom2, d2),
					)
				}
			default:
				return fmt.Errorf("--min-collateral-ratio accepts 0, 1, or 2 values")
			}

			// fee-rate: 0 => keep current. 1/2 => parse and set
			var feeRate sdk.DecCoins
			switch len(feeRateFlags) {
			case 0:
				feeRate = sdk.NewDecCoins(pool.FeeRate...)
			case 1:
				dc, perr := sdk.ParseDecCoin(strings.TrimSpace(feeRateFlags[0]))
				if perr != nil {
					return fmt.Errorf("invalid --fee-rate '%s': %w", feeRateFlags[0], perr)
				}
				feeRate = sdk.NewDecCoins(dc)
			case 2:
				parsed := make([]sdk.DecCoin, 0, 2)
				for _, v := range feeRateFlags {
					dc, perr := sdk.ParseDecCoin(strings.TrimSpace(v))
					if perr != nil {
						return fmt.Errorf("invalid --fee-rate '%s': %w", v, perr)
					}
					parsed = append(parsed, dc)
				}
				feeRate = sdk.NewDecCoins(parsed...)
			default:
				return fmt.Errorf("--fee-rate must be provided 0, 1, or 2 times (per-denom fee as DecCoin)")
			}

			boundFlags, err := cmd.Flags().GetStringArray("bound-percent")
			if err != nil {
				return fmt.Errorf("failed to read --bound-percent: %w", err)
			}
			var boundPercent sdk.DecCoins
			switch len(boundFlags) {
			case 0:
				// leave empty to skip update
			case 2:
				if parsed, ok := tryParseDecCoins(boundFlags); ok {
					if len(parsed) != 2 || parsed[0].Denom != pool.Coins[0].Denom || parsed[1].Denom != pool.Coins[1].Denom {
						return fmt.Errorf("--bound-percent DecCoins must match pool denoms in canonical order (%s,%s)", pool.Coins[0].Denom, pool.Coins[1].Denom)
					}
					zero := smath.LegacyZeroDec()
					oneDec := smath.LegacyNewDec(1)
					for _, dc := range parsed {
						if !dc.Amount.GT(zero) || dc.Amount.GT(oneDec) {
							return fmt.Errorf("--bound-percent amounts must satisfy 0 < x <= 1; invalid entry for %s", dc.Denom)
						}
					}
					boundPercent = parsed
				} else {
					b1 := mustDec(strings.TrimSpace(boundFlags[0]))
					b2 := mustDec(strings.TrimSpace(boundFlags[1]))
					zero := smath.LegacyZeroDec()
					oneDec := smath.LegacyNewDec(1)
					if !b1.GT(zero) || b1.GT(oneDec) {
						return fmt.Errorf("--bound-percent value for %s must satisfy 0 < x <= 1", pool.Coins[0].Denom)
					}
					if !b2.GT(zero) || b2.GT(oneDec) {
						return fmt.Errorf("--bound-percent value for %s must satisfy 0 < x <= 1", pool.Coins[1].Denom)
					}
					boundPercent = sdk.NewDecCoins(
						sdk.NewDecCoinFromDec(pool.Coins[0].Denom, b1),
						sdk.NewDecCoinFromDec(pool.Coins[1].Denom, b2),
					)
				}
			default:
				return fmt.Errorf("--bound-percent accepts exactly two values (one per denom) when provided")
			}

			msg := &whaleswaptypes.MsgUpdatePoolConfig{
				Signer:                    clientCtx.GetFromAddress().String(),
				PoolId:                    poolID,
				FeeRate:                   feeRate,
				InterestRate:              interestRate,
				MaxBorrowPercent:          maxBorrowPercent,
				LiquidationThreshold:      liquidationThreshold,
				MinInitialCollateralRatio: minCollateralRatio,
				BoundPercent:              boundPercent,
			}
			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}
	cmd.Flags().Uint64("pool-id", 0, "Pool ID")
	if err := cmd.MarkFlagRequired("pool-id"); err != nil {
		panic(fmt.Errorf("failed to mark --pool-id required: %w", err))
	}
	cmd.Flags().StringArray("fee-rate", nil, "Repeatable (0, 1, or 2); per-denom swap fee as DecCoin in [0,1) (e.g., 0.003udys)")
	cmd.Flags().StringArray("interest-rate", nil, "Repeatable (0, 1, or 2); APR per denom as DecCoin (e.g., 0.10udys). Optional; defaults to current values when omitted")
	cmd.Flags().StringArray("max-borrow-percent", nil, "Repeatable (0, 1, or 2); max borrow percent per denom. Optional; defaults to current values when omitted")
	cmd.Flags().String("liquidation-threshold", "", "Liquidation threshold (cosmos.Dec). Optional; defaults to current pool")
	cmd.Flags().String("min-collateral-ratio", "", "Minimum collateral ratio for leverage. Optional; defaults to current pool")
	cmd.Flags().StringArray("bound-percent", nil, "Repeatable (optional); provide two decimals or DecCoins specifying max fractional price drop per sold denom (0 < x <= 1). Omit to keep current bounds")
	flags.AddTxFlagsToCmd(cmd)
	return cmd
}

// helpers to fallback to existing values when empty
func ifEmptyUse(s, fallback string) string {
	if strings.TrimSpace(s) == "" {
		return fallback
	}
	return s
}

// helper dec parsing
func mustDec(s string) smath.LegacyDec {
	d, err := smath.LegacyNewDecFromStr(s)
	if err != nil {
		panic(fmt.Errorf("invalid decimal '%s': %w", s, err))
	}
	return d
}

func tryParseDecCoins(vals []string) (sdk.DecCoins, bool) {
	out := make([]sdk.DecCoin, 0, len(vals))
	for _, v := range vals {
		dc, err := sdk.ParseDecCoin(strings.TrimSpace(v))
		if err != nil {
			return sdk.DecCoins{}, false
		}
		out = append(out, dc)
	}
	return sdk.NewDecCoins(out...), true
}

// CmdCoverPosition covers accrued interest and optionally reduces principal; overpay auto-closes.
func CmdCoverPosition() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "cover-position",
		Short: "Repay interest and optionally principal on a leverage position (overpay closes)",
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientTxContext(cmd)
			if err != nil {
				return err
			}
			posID, err := cmd.Flags().GetUint64("position-id")
			if err != nil {
				return err
			}
			payStr, err := cmd.Flags().GetString("payment")
			if err != nil {
				return err
			}
			payment, perr := sdk.ParseCoinNormalized(strings.TrimSpace(payStr))
			if perr != nil {
				return fmt.Errorf("invalid --payment coin '%s': %w", payStr, perr)
			}
			note, err := cmd.Flags().GetString("position-note")
			if err != nil {
				return err
			}
			msg := &whaleswaptypes.MsgCoverPosition{
				User:       clientCtx.GetFromAddress().String(),
				PositionId: posID,
				Payment:    payment,
				Note:       note,
			}
			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}
	cmd.Flags().Uint64("position-id", 0, "Leverage position ID")
	if err := cmd.MarkFlagRequired("position-id"); err != nil {
		panic(fmt.Errorf("failed to mark --position-id required: %w", err))
	}
	cmd.Flags().String("payment", "", "Payment coin (borrowed denom), e.g., 100udys")
	if err := cmd.MarkFlagRequired("payment"); err != nil {
		panic(fmt.Errorf("failed to mark --payment required: %w", err))
	}
	cmd.Flags().String("position-note", "", "Optional note echoed to internal swaps")
	flags.AddTxFlagsToCmd(cmd)
	return cmd
}
