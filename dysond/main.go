package main

import (
	"fmt"
	"os"

	"dysonprotocol.com"
	cmd "dysonprotocol.com/dysond/cmd"
	"dysonprotocol.com/dysvm"

	svrcmd "github.com/cosmos/cosmos-sdk/server/cmd"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

func main() {
	cfg := sdk.GetConfig()
	// Allow 1-127 character denoms (first char letter, then 0-126 of allowed charset)
	sdk.SetCoinDenomRegex(func() string { return `[a-zA-Z][a-zA-Z0-9/:._-]{0,126}` })
	cfg.SetBech32PrefixForAccount("dys2", "dys2pub")                     // account addresses
	cfg.SetBech32PrefixForValidator("dys2valoper", "dys2valoperpub")     // validator operator addresses
	cfg.SetBech32PrefixForConsensusNode("dys2valcons", "dys2valconspub") // consensus addresses

	rootCmd := cmd.NewRootCmd()
	err := svrcmd.Execute(rootCmd, "DYSON", dysonprotocol.DefaultNodeHome)
	dysvm.ShutdownServer()
	if err != nil {
		fmt.Fprintln(rootCmd.OutOrStderr(), err)
		os.Exit(1)
	}
}
