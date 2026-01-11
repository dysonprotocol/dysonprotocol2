package main

import (
	"fmt"
	"os"

	"dysonprotocol.com"
	cmd "dysonprotocol.com/dysond/cmd"
	"dysonprotocol.com/dysond/params"
	"dysonprotocol.com/dysvm"

	svrcmd "github.com/cosmos/cosmos-sdk/server/cmd"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// Chain identity constants - these are hardcoded per binary as is standard in Cosmos SDK.
// The base denom is set via sdk.DefaultBondDenom before DefaultGenesis() is called.
// The name suffix is stored in nameservice genesis params.
const (
	Bech32PrefixAccount      = params.DefaultBech32Prefix
	Bech32PrefixAccountPub   = Bech32PrefixAccount + "pub"
	Bech32PrefixValidator    = Bech32PrefixAccount + "valoper"
	Bech32PrefixValidatorPub = Bech32PrefixAccount + "valoperpub"
	Bech32PrefixConsensus    = Bech32PrefixAccount + "valcons"
	Bech32PrefixConsensusPub = Bech32PrefixAccount + "valconspub"
)

// DefaultBaseDenom is the base denomination for the native token.
// This is set before DefaultGenesis() is called so all modules use this denom.
const DefaultBaseDenom = params.DefaultBaseDenom

func main() {
	// Configure SDK with chain identity (bech32 prefixes are hardcoded in binary)
	cfg := sdk.GetConfig()
	// Allow 1-127 character denoms (first char letter, then 0-126 of allowed charset)
	sdk.SetCoinDenomRegex(func() string { return `[a-zA-Z][a-zA-Z0-9/:._-]{0,126}` })
	cfg.SetBech32PrefixForAccount(Bech32PrefixAccount, Bech32PrefixAccountPub)
	cfg.SetBech32PrefixForValidator(Bech32PrefixValidator, Bech32PrefixValidatorPub)
	cfg.SetBech32PrefixForConsensusNode(Bech32PrefixConsensus, Bech32PrefixConsensusPub)

	// Set the default bond denom before any genesis operations
	// This is used by staking, gov, and other modules for their default params
	sdk.DefaultBondDenom = DefaultBaseDenom

	rootCmd := cmd.NewRootCmd()
	err := svrcmd.Execute(rootCmd, "DYSON", dysonprotocol.DefaultNodeHome)
	dysvm.ShutdownServer()
	if err != nil {
		fmt.Fprintln(rootCmd.OutOrStderr(), err)
		os.Exit(1)
	}
}
