package cli

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/client/tx"
	sdk "github.com/cosmos/cosmos-sdk/types"

	whaleswaptypes "dysonprotocol.com/x/whaleswap/types"
)

// CmdTakeOffer provides a custom CLI for taking one or more offers using a repeatable
// string array flag. Each occurrence encodes a single TakeItem in a simple key=value format.
//
// Usage examples:
//
//	dysond tx whaleswap take-offer \
//	  --trades "offer_id=1" \
//	  --trades "offer_id=2,take_units=10" \
//	  --from alice
//
// Accepted keys per item:
//   - offer_id (required)
//   - take_units (optional; defaults to full remaining)
func CmdTakeOffer() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "take-offer",
		Short: "Take one or more offers (batch)",
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientTxContext(cmd)
			if err != nil {
				return err
			}

			tradeSpecs, err := cmd.Flags().GetStringArray("trades")
			if err != nil {
				return err
			}
			if len(tradeSpecs) == 0 {
				return fmt.Errorf("at least one --trades entry is required; format 'offer_id=<id>[,take_units=<int>]' and repeat the flag per item")
			}

			items := make([]whaleswaptypes.TakeItem, 0, len(tradeSpecs))
			for _, spec := range tradeSpecs {
				spec = strings.TrimSpace(spec)
				if spec == "" {
					return fmt.Errorf("empty --trades entry")
				}
				var offerIDStr string
				var takeUnits string
				parts := strings.Split(spec, ",")
				for _, p := range parts {
					kv := strings.SplitN(strings.TrimSpace(p), "=", 2)
					if len(kv) != 2 {
						return fmt.Errorf("invalid --trades entry '%s' (want key=value pairs)", spec)
					}
					key := strings.TrimSpace(kv[0])
					val := strings.TrimSpace(kv[1])
					switch key {
					case "offer_id", "offerId":
						offerIDStr = val
					case "take_units", "takeUnits":
						takeUnits = val
					default:
						return fmt.Errorf("unknown key '%s' in --trades entry '%s'", key, spec)
					}
				}
				if offerIDStr == "" {
					return fmt.Errorf("offer_id is required in --trades entry '%s'", spec)
				}
				items = append(items, whaleswaptypes.TakeItem{OfferId: parseUintOrPanic(offerIDStr), TakeUnits: takeUnits})
			}

			msg := &whaleswaptypes.MsgTakeOffer{
				Taker:  clientCtx.GetFromAddress().String(),
				Trades: items,
			}
			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}

	cmd.Flags().StringArray("trades", nil, "Repeatable; format 'offer_id=<id>[,take_units=<int>]' (repeat flag per item)")
	// take mode removed; TAKE_ALL implicit
	flags.AddTxFlagsToCmd(cmd)
	return cmd
}

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

// CmdCreatePool provides custom parsing for repeated --coins/--min-price/--max-price flags.
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
			feePct, err := cmd.Flags().GetString("fee-pct")
			if err != nil {
				return fmt.Errorf("failed to read --fee-pct: %w", err)
			}
			minFlags, err := cmd.Flags().GetStringArray("min-price")
			if err != nil {
				return fmt.Errorf("failed to read --min-price flags: %w", err)
			}
			maxFlags, err := cmd.Flags().GetStringArray("max-price")
			if err != nil {
				return fmt.Errorf("failed to read --max-price flags: %w", err)
			}

			var minPrice, maxPrice []sdk.Coin
			if len(minFlags) > 0 || len(maxFlags) > 0 {
				if len(minFlags) != 2 || len(maxFlags) != 2 {
					return fmt.Errorf("when setting bands, provide exactly two --min-price and two --max-price flags (one coin per flag)")
				}
				if minPrice, err = parseCoinList("min-price", minFlags); err != nil {
					return err
				}
				if maxPrice, err = parseCoinList("max-price", maxFlags); err != nil {
					return err
				}
			}

			minCollateralRatio, err := cmd.Flags().GetString("min-collateral-ratio")
			if err != nil {
				return fmt.Errorf("failed to read --min-collateral-ratio: %w", err)
			}
			maxLeverageRatio, err := cmd.Flags().GetString("max-leverage-ratio")
			if err != nil {
				return fmt.Errorf("failed to read --max-leverage-ratio: %w", err)
			}
			maxBorrowPercent, err := cmd.Flags().GetString("max-borrow-percent")
			if err != nil {
				return fmt.Errorf("failed to read --max-borrow-percent: %w", err)
			}

			msg := &whaleswaptypes.MsgCreatePool{
				Creator:            clientCtx.GetFromAddress().String(),
				Coins:              coinList,
				MinPrice:           minPrice,
				MaxPrice:           maxPrice,
				FeePct:             feePct,
				MinCollateralRatio: minCollateralRatio,
				MaxLeverageRatio:   maxLeverageRatio,
				MaxBorrowPercent:   maxBorrowPercent,
			}
			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}
	cmd.Flags().StringArray("coins", nil, "Repeatable; provide exactly two flags, one per coin (e.g., 1000udys)")
	cmd.Flags().String("fee-pct", "", "Optional swap fee percent (decimal in [0,1))")
	cmd.Flags().StringArray("min-price", nil, "Repeatable; provide two flags to encode band min as coin_b/coin_a")
	cmd.Flags().StringArray("max-price", nil, "Repeatable; provide two flags to encode band max as coin_b/coin_a")
	cmd.Flags().String("min-collateral-ratio", "", "Minimum collateral ratio for leverage (required, e.g., 1.5)")
	cmd.Flags().String("max-leverage-ratio", "", "Maximum leverage ratio (required, e.g., 3.0)")
	cmd.Flags().String("max-borrow-percent", "", "Maximum borrow percent of reserves (required, e.g., 0.8)")
	flags.AddTxFlagsToCmd(cmd)
	return cmd
}

// CmdUpdatePoolConfig provides custom parsing for repeated band flags.
func CmdUpdatePoolConfig() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "update-pool-config",
		Short: "Update pool fee or price band",
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientTxContext(cmd)
			if err != nil {
				return err
			}
			poolID, err := cmd.Flags().GetUint64("pool-id")
			if err != nil {
				return err
			}
			feePct, err := cmd.Flags().GetString("fee-pct")
			if err != nil {
				return fmt.Errorf("failed to read --fee-pct: %w", err)
			}
			minFlags, err := cmd.Flags().GetStringArray("min-price")
			if err != nil {
				return fmt.Errorf("failed to read --min-price flags: %w", err)
			}
			maxFlags, err := cmd.Flags().GetStringArray("max-price")
			if err != nil {
				return fmt.Errorf("failed to read --max-price flags: %w", err)
			}

			var minPrice, maxPrice []sdk.Coin
			if len(minFlags) > 0 || len(maxFlags) > 0 {
				if len(minFlags) != 2 || len(maxFlags) != 2 {
					return fmt.Errorf("when setting bands, provide exactly two --min-price and two --max-price flags (one coin per flag)")
				}
				if minPrice, err = parseCoinList("min-price", minFlags); err != nil {
					return err
				}
				if maxPrice, err = parseCoinList("max-price", maxFlags); err != nil {
					return err
				}
			}

			ir1, err := cmd.Flags().GetString("interest-rate-coin1")
			if err != nil {
				return fmt.Errorf("failed to read --interest-rate-coin1: %w", err)
			}
			ir2, err := cmd.Flags().GetString("interest-rate-coin2")
			if err != nil {
				return fmt.Errorf("failed to read --interest-rate-coin2: %w", err)
			}

			msg := &whaleswaptypes.MsgUpdatePoolConfig{
				Signer:            clientCtx.GetFromAddress().String(),
				PoolId:            poolID,
				FeePct:            feePct,
				MinPrice:          minPrice,
				MaxPrice:          maxPrice,
				InterestRateCoin1: ir1,
				InterestRateCoin2: ir2,
			}
			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}
	cmd.Flags().Uint64("pool-id", 0, "Pool ID")
	if err := cmd.MarkFlagRequired("pool-id"); err != nil {
		panic(fmt.Errorf("failed to mark --pool-id required: %w", err))
	}
	cmd.Flags().String("fee-pct", "", "Optional swap fee percent (decimal in [0,1))")
	cmd.Flags().StringArray("min-price", nil, "Repeatable; provide two flags to encode band min as coin_b/coin_a")
	cmd.Flags().StringArray("max-price", nil, "Repeatable; provide two flags to encode band max as coin_b/coin_a")
	cmd.Flags().String("interest-rate-coin1", "", "Optional APR for coin1 (decimal, e.g., 0.10 for 10%)")
	cmd.Flags().String("interest-rate-coin2", "", "Optional APR for coin2 (decimal, e.g., 0.10 for 10%)")
	flags.AddTxFlagsToCmd(cmd)
	return cmd
}
