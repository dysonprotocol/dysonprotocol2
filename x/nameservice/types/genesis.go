package types

import (
	"fmt"
)

// DefaultGenesis returns default genesis state as raw bytes for the nameservice module
func DefaultGenesis() *GenesisState {
	return &GenesisState{
		Params:      DefaultParams(),
		Commitments: []Commitment{},
		BidSeq:      0,
		Bids:        []BidRecord{},
	}
}

// ValidateGenesis validates the provided genesis state to ensure the
// expected invariants holds.
func ValidateGenesis(data *GenesisState) error {
	// Validate params
	if err := data.Params.Validate(); err != nil {
		return err
	}

	// Validate commitments
	commitmentMap := make(map[string]bool)
	for _, commitment := range data.Commitments {
		if commitment.Hexhash == "" {
			return fmt.Errorf("empty commitment hash")
		}
		if commitmentMap[commitment.Hexhash] {
			return fmt.Errorf("duplicate commitment found: %s", commitment.Hexhash)
		}
		commitmentMap[commitment.Hexhash] = true
	}

	// Validate bids: unique IDs, non-empty class and nft ids
	seen := make(map[uint64]bool)
	for _, b := range data.Bids {
		if b.BidId == 0 {
			return fmt.Errorf("bid_id cannot be zero")
		}
		if seen[b.BidId] {
			return fmt.Errorf("duplicate bid_id in genesis: %d", b.BidId)
		}
		seen[b.BidId] = true
		if b.ClassId == "" || b.NftId == "" || b.Bidder == "" {
			return fmt.Errorf("invalid bid record %d: empty class_id/nft_id/bidder", b.BidId)
		}
		if b.Amount.Denom == "" || !b.Amount.Amount.IsPositive() {
			return fmt.Errorf("invalid bid amount for bid %d", b.BidId)
		}
	}

	return nil
}
