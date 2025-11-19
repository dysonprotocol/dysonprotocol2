package whaleswap

import (
	"fmt"

	cosmossdk_math "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"dysonprotocol.com/x/whaleswap/types"
)

// NewGenesisState creates a new genesis state with default values.
func NewGenesisState() *types.GenesisState {
	return &types.GenesisState{
		Params: types.DefaultParams(),
	}
}

// DefaultGenesis returns default genesis state for the whaleswap module
func DefaultGenesis() *types.GenesisState { return NewGenesisState() }

// ValidateGenesisState performs comprehensive genesis validation.
func ValidateGenesisState(s types.GenesisState) error {
	s.Params = types.MigrateParams(s.Params)
	if err := s.Params.Validate(); err != nil {
		return err
	}

	// Pools
	seenPools := map[uint64]struct{}{}
	for _, p := range s.Pools {
		if p == nil {
			return fmt.Errorf("nil pool entry in genesis")
		}
		if _, dup := seenPools[p.PoolId]; dup {
			return fmt.Errorf("duplicate pool_id: %d", p.PoolId)
		}
		seenPools[p.PoolId] = struct{}{}

		if len(p.Coins) != 2 {
			return fmt.Errorf("pool %d must have exactly 2 coins", p.PoolId)
		}
		a := p.Coins[0]
		b := p.Coins[1]
		if a.Denom == "" || b.Denom == "" {
			return fmt.Errorf("pool %d coins must have non-empty denoms", p.PoolId)
		}
		if !(a.Denom < b.Denom) {
			return fmt.Errorf("pool %d coins must be in canonical order (denom[0] < denom[1])", p.PoolId)
		}
		if !a.Amount.IsPositive() || !b.Amount.IsPositive() {
			return fmt.Errorf("pool %d coin amounts must be positive", p.PoolId)
		}
		if p.SharesDenom == "" {
			return fmt.Errorf("pool %d shares_denom must be set", p.PoolId)
		}
		if len(p.FeeRate) != 2 {
			return fmt.Errorf("pool %d fee_rate must have exactly two entries", p.PoolId)
		}
		fr1 := p.FeeRate.AmountOf(a.Denom)
		fr2 := p.FeeRate.AmountOf(b.Denom)
		if fr1.IsNegative() || !fr1.LT(cosmossdk_math.LegacyNewDec(1)) || fr2.IsNegative() || !fr2.LT(cosmossdk_math.LegacyNewDec(1)) {
			return fmt.Errorf("pool %d fee_rate amounts must be in [0,1)", p.PoolId)
		}
		// Validate bound_percent: optional, supports up to two entries matching pool denoms with amounts in (0,1]
		if len(p.BoundPercent) > 2 {
			return fmt.Errorf("pool %d bound_percent must contain at most 2 entries", p.PoolId)
		}
		for _, bc := range p.BoundPercent {
			if bc.Denom != a.Denom && bc.Denom != b.Denom {
				return fmt.Errorf("pool %d bound_percent denom %s must match pool denoms", p.PoolId, bc.Denom)
			}
			if !bc.Amount.GT(cosmossdk_math.LegacyZeroDec()) || bc.Amount.GT(cosmossdk_math.LegacyNewDec(1)) {
				return fmt.Errorf("pool %d bound_percent amount must satisfy 0 < x <= 1", p.PoolId)
			}
		}
		bp1 := p.BoundPercent.AmountOf(a.Denom)
		bp2 := p.BoundPercent.AmountOf(b.Denom)
		if bp1.IsZero() {
			bp1 = cosmossdk_math.LegacyNewDec(1)
		}
		if bp2.IsZero() {
			bp2 = cosmossdk_math.LegacyNewDec(1)
		}
	}

	// Offers
	seenOffers := map[uint64]struct{}{}
	for _, o := range s.Offers {
		if o == nil {
			return fmt.Errorf("nil offer entry in genesis")
		}
		if _, dup := seenOffers[o.OfferId]; dup {
			return fmt.Errorf("duplicate offer_id: %d", o.OfferId)
		}
		seenOffers[o.OfferId] = struct{}{}

		switch o.Status {
		case types.OfferStatusOpen, types.OfferStatusClosed, types.OfferStatusCancelled:
		default:
			return fmt.Errorf("offer %d invalid status: %s", o.OfferId, o.Status)
		}
		if o.Maker == "" {
			return fmt.Errorf("offer %d maker cannot be empty", o.OfferId)
		}
		if _, err := sdk.AccAddressFromBech32(o.Maker); err != nil {
			return fmt.Errorf("offer %d maker address invalid: %v", o.OfferId, err)
		}
		// initial have/want must be set and positive
		if o.InitialHave.Denom == "" || o.InitialWant.Denom == "" {
			return fmt.Errorf("offer %d initial coins must have non-empty denoms", o.OfferId)
		}
		if !o.InitialHave.Amount.IsPositive() || !o.InitialWant.Amount.IsPositive() {
			return fmt.Errorf("offer %d initial coin amounts must be positive", o.OfferId)
		}
		// remaining denoms must match initials
		if o.RemainingHave.Denom == "" || o.RemainingWant.Denom == "" {
			return fmt.Errorf("offer %d remaining coins must have non-empty denoms", o.OfferId)
		}
		if o.RemainingHave.Denom != o.InitialHave.Denom || o.RemainingWant.Denom != o.InitialWant.Denom {
			return fmt.Errorf("offer %d remaining denoms must match initial denoms", o.OfferId)
		}
		if o.Status == types.OfferStatusOpen {
			if !o.RemainingHave.Amount.IsPositive() || !o.RemainingWant.Amount.IsPositive() {
				return fmt.Errorf("offer %d remaining amounts must be positive for open offers", o.OfferId)
			}
		}
	}

	// Trades
	seenTrades := map[uint64]struct{}{}
	for _, t := range s.Trades {
		if t == nil {
			return fmt.Errorf("nil trade entry in genesis")
		}
		if _, dup := seenTrades[t.TradeId]; dup {
			return fmt.Errorf("duplicate trade_id: %d", t.TradeId)
		}
		seenTrades[t.TradeId] = struct{}{}
		if t.Trader == "" {
			return fmt.Errorf("trade %d trader cannot be empty", t.TradeId)
		}
		if _, err := sdk.AccAddressFromBech32(t.Trader); err != nil {
			return fmt.Errorf("trade %d trader address invalid: %v", t.TradeId, err)
		}
		if len(t.Operations) == 0 {
			return fmt.Errorf("trade %d must have at least one operation", t.TradeId)
		}
	}

	// Auctions
	seenAuctions := map[uint64]struct{}{}
	for _, a := range s.Auctions {
		if a == nil {
			return fmt.Errorf("nil auction entry in genesis")
		}
		if _, dup := seenAuctions[a.AuctionId]; dup {
			return fmt.Errorf("duplicate auction_id: %d", a.AuctionId)
		}
		seenAuctions[a.AuctionId] = struct{}{}
		if a.ClassId == "" || a.NftId == "" {
			return fmt.Errorf("auction %d must have class_id and nft_id", a.AuctionId)
		}
		if a.Sell.Denom == "" || !a.Sell.Amount.IsPositive() {
			return fmt.Errorf("auction %d sell coin must have denom and positive amount", a.AuctionId)
		}
		if a.BidDenom == "" {
			return fmt.Errorf("auction %d bid_denom must be set", a.AuctionId)
		}
		if a.Seller == "" {
			return fmt.Errorf("auction %d seller cannot be empty", a.AuctionId)
		}
		if _, err := sdk.AccAddressFromBech32(a.Seller); err != nil {
			return fmt.Errorf("auction %d seller address invalid: %v", a.AuctionId, err)
		}
	}

	// Leverage Positions
	seenPositions := map[uint64]struct{}{}
	for _, p := range s.Positions {
		if p == nil {
			return fmt.Errorf("nil position entry in genesis")
		}
		if _, dup := seenPositions[p.PositionId]; dup {
			return fmt.Errorf("duplicate position_id: %d", p.PositionId)
		}
		seenPositions[p.PositionId] = struct{}{}

		if p.User == "" {
			return fmt.Errorf("position %d user cannot be empty", p.PositionId)
		}
		if _, err := sdk.AccAddressFromBech32(p.User); err != nil {
			return fmt.Errorf("position %d user address invalid: %v", p.PositionId, err)
		}
		if p.PoolId == 0 {
			return fmt.Errorf("position %d pool_id must be set", p.PositionId)
		}
		// Validate coins are non-negative
		if p.Borrowed.Amount.IsNegative() {
			return fmt.Errorf("position %d borrowed amount must be non-negative", p.PositionId)
		}
		if p.Held.Amount.IsNegative() {
			return fmt.Errorf("position %d held amount must be non-negative", p.PositionId)
		}
		if p.Collateral.Amount.IsNegative() {
			return fmt.Errorf("position %d collateral amount must be non-negative", p.PositionId)
		}
		if p.AccruedInterest.Amount.IsNegative() {
			return fmt.Errorf("position %d accrued_interest amount must be non-negative", p.PositionId)
		}
		// Validate liquidation status
		switch p.LiquidationStatus {
		case types.LiquidationStatus_LIQUIDATION_STATUS_UNSPECIFIED,
			types.LiquidationStatus_LIQUIDATION_STATUS_NONE,
			types.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED:
		default:
			return fmt.Errorf("position %d invalid liquidation_status: %v", p.PositionId, p.LiquidationStatus)
		}
		// Validate min_collateral_ratio is a valid decimal (per-position snapshot)
		if p.MinCollateralRatio != "" {
			if _, err := cosmossdk_math.LegacyNewDecFromStr(p.MinCollateralRatio); err != nil {
				return fmt.Errorf("position %d invalid min_collateral_ratio: %v", p.PositionId, err)
			}
		}
	}

	return nil
}
