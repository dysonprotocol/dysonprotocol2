package main

import (
	"context"
	"fmt"

	"dysonprotocol.com/dysvm"

	"github.com/kluctl/go-embed-python/python"
)

func main() {
	// Make a simple hello world script example

	msgJSON := `
	{
	  "@type": "/dysonprotocol.script.v1.MsgExec",
	  "executor_address": "dys1zh037hy4vfxhferrt6uzrarwss3wxkwhhuj0z0",
	  "script_address": "dys1zh037hy4vfxhferrt6uzrarwss3wxkwhhuj0z0",
	  "extra_code": "def foo(a, b): return foo, a, b",
	  "function_name": "foo",
	  "args": "[1, 2]",
	  "kwargs": "{}",
	  "attached_messages": []
	}
	`

	scriptJSON := `
	{
	  "address": "dys1zh037hy4vfxhferrt6uzrarwss3wxkwhhuj0z0",
	  "version": "1",
	  "code": ""
	}
	`

	attachedMsgResultsJSON := `[]`

	headerInfoJSON := `{"Height":48032,"Hash":"bQsQcbehZBNQJ+G1g1PRruQgkzBC027A9GfYhp5UjcQ=","Time":"2025-01-19T08:17:59Z","AppHash":"RWh3CJ9RED+tTdhi57N8u9TKYfm5wbkiAlRI3kMQICU=","ChainID":"demo"}`

	// func Exec(msgJSON, scriptJSON, attachedMsgResultsJSON, headerInfoJSON, port string) (string, error) {
	out, err := dysvm.Exec(

		context.Background(),
		msgJSON, scriptJSON, attachedMsgResultsJSON, headerInfoJSON, "0")

	fmt.Println("out: ", out)
	fmt.Println("err: ", err)

	if err != nil {
		panic(err)
	}

	// python version
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
	}
	cmd, err := ep.PythonCmd("--version")
	if err != nil {
		panic(err)
	}
	runOut, runErr := cmd.CombinedOutput()
	fmt.Println("Command output: ", string(runOut))
	fmt.Println("Command error: ", runErr)

}
