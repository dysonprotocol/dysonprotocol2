package script

import (
	"fmt"

	"dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	gogoprotoany "github.com/cosmos/gogoproto/types/any"
)

// NewGenesisState creates a new genesis state
func NewGenesisState() *types.GenesisState {
	return &types.GenesisState{
		Params: types.DefaultParams(),
	}
}

// ValidateGenesis validates the genesis state
func ValidateGenesis(s *types.GenesisState) error {
	if err := s.Params.Validate(); err != nil {
		return err
	}
	seen := make(map[string]struct{})
	for _, sc := range s.Scripts {
		if sc == nil {
			return fmt.Errorf("nil script entry in genesis")
		}
		if sc.Address == "" {
			return fmt.Errorf("script address cannot be empty")
		}
		if _, err := sdk.AccAddressFromBech32(sc.Address); err != nil {
			return fmt.Errorf("invalid script address %s: %v", sc.Address, err)
		}
		if _, dup := seen[sc.Address]; dup {
			return fmt.Errorf("duplicate script address %s", sc.Address)
		}
		seen[sc.Address] = struct{}{}
	}
	return nil
}

// UnpackInterfaces implements UnpackInterfacesMessage.UnpackInterfaces
func UnpackGenesisInterfaces(s *types.GenesisState, unpacker gogoprotoany.AnyUnpacker) error {
	return nil
}
