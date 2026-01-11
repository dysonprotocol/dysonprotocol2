package params

import (
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	"github.com/cosmos/cosmos-sdk/codec/types"
)

// Chain identity constants
const (
	DefaultBech32Prefix = "dys2"
	DefaultNameSuffix   = ".dys"
	DefaultBaseDenom    = "udys"
	DefaultDisplayDenom = "DYS2"
)

// Simulation parameters for Dyson Protocol
const (
	DefaultNumBlocks   = 500
	DefaultBlockSize   = 200
	DefaultChainID     = "dyson_9000-1"
	DefaultHomeDir     = ".dysond"
	DefaultGenesisTime = 1614556800 // Feb 28, 2021 16:00:00 UTC
)

// DefaultNodeHome returns the default home directory for the node
func DefaultNodeHome() string {
	return DefaultHomeDir
}

// EncodingConfig specifies the concrete encoding types to use for a given app.
// This is provided for compatibility between protobuf and amino implementations.
type EncodingConfig struct {
	InterfaceRegistry types.InterfaceRegistry
	Codec             codec.Codec
	TxConfig          client.TxConfig
	Amino             *codec.LegacyAmino
}
