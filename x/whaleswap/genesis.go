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
		if p.FeePct != "" {
			dec, err := cosmossdk_math.LegacyNewDecFromStr(p.FeePct)
			if err != nil {
				return fmt.Errorf("pool %d invalid fee_pct: %v", p.PoolId, err)
			}
			if dec.IsNegative() || !dec.LT(cosmossdk_math.LegacyNewDec(1)) {
				return fmt.Errorf("pool %d fee_pct must be in [0,1)", p.PoolId)
			}
		}
		// Validate price band coins if provided
		if len(p.MinPrice) != 0 && len(p.MinPrice) != 2 {
			return fmt.Errorf("pool %d min_price must be empty or contain exactly 2 coins", p.PoolId)
		}
		if len(p.MaxPrice) != 0 && len(p.MaxPrice) != 2 {
			return fmt.Errorf("pool %d max_price must be empty or contain exactly 2 coins", p.PoolId)
		}
		if len(p.MinPrice) == 2 {
			if p.MinPrice[0].Denom != a.Denom || p.MinPrice[1].Denom != b.Denom {
				return fmt.Errorf("pool %d min_price denoms must match coins[0]/coins[1]", p.PoolId)
			}
			if !p.MinPrice[0].Amount.IsPositive() || !p.MinPrice[1].Amount.IsPositive() {
				return fmt.Errorf("pool %d min_price amounts must be positive", p.PoolId)
			}
		}
		if len(p.MaxPrice) == 2 {
			if p.MaxPrice[0].Denom != a.Denom || p.MaxPrice[1].Denom != b.Denom {
				return fmt.Errorf("pool %d max_price denoms must match coins[0]/coins[1]", p.PoolId)
			}
			if !p.MaxPrice[0].Amount.IsPositive() || !p.MaxPrice[1].Amount.IsPositive() {
				return fmt.Errorf("pool %d max_price amounts must be positive", p.PoolId)
			}
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

	return nil
}
