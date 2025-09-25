package cli

import (
	"context"
	"errors"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
)

// GetQueryCmd returns the cli query commands for this module
func GetQueryCmd() *cobra.Command {
	queryCmd := &cobra.Command{
		Use:                        "script",
		Short:                      "Querying commands for the script module",
		DisableFlagParsing:         true,
		SuggestionsMinimumDistance: 2,
		RunE:                       client.ValidateCmd,
	}

	queryCmd.AddCommand(
		GetCmdQueryRun(),
		GetCmdQueryScriptInfo(),
		GetCmdQueryBenchmark(),
	)

	return queryCmd
}

// GetCmdQueryRun returns the command to query script run
func GetCmdQueryRun() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "run --script-address <script_address> [--executor-address <executor_address>] [--args <input_data>] [--function-name <function_name>] [--extra-code <extra_code> | --extra-code-path <path>] [--kwargs <keyword_args>] [--attached-message <message>]",
		Short: "Execute a script at a given address with optional input data and other parameters",
		Long: `Executes a script at a given address with optional input data and other parameters.

Required Flags:
  --script-address: The address of the script to execute (can be a bech32 address or a nameservice name like 'example.dys')

Optional Flags:
  --executor-address: The address of the executor account (account address or key name)
  --args: Positional arguments to pass to the function as a JSON list (e.g., '["arg1", "arg2"]')
  --function-name: The name of the function to run (defaults to a main or entry point function if not specified)
  --extra-code: Additional code to temporarily append to the script for this execution (only allowed if the executor is the owner of the script)
  --extra-code-path: Path to a file containing additional code to temporarily append to the script (only allowed if the executor is the owner of the script)
  --kwargs: Keyword arguments to pass to the function as a JSON dictionary (e.g., '{"key1": "value1", "key2": "value2"}')
  --attached-message: Attached messages to include in the execution as JSON (can be used multiple times)

Examples:
  # Execute a script with minimal parameters
  $ dysond query script run --script-address dys2123...

  # Execute a script with input data as positional arguments
  $ dysond query script run --script-address dys2123... --args '["arg1", "arg2"]'

  # Execute a script with a specific function name and keyword arguments
  $ dysond query script run --script-address dys2123... --function-name "process_data" --kwargs '{"input_type": "json", "verbose": true}'

  # Execute a script with extra code (if executor is the owner)
  $ dysond query script run --script-address dys2123... --extra-code "def helper(): return 'temp help';"

  # Execute a script with extra code from a file (if executor is the owner)
  $ dysond query script run --script-address dys2123... --extra-code-path ./helper_functions.py

  # Execute a script with attached messages
  $ dysond query script run --script-address dys2123... --attached-message '{"@type":"/cosmos.bank.v1beta1.MsgSend","from_address":"dys2123...","to_address":"dys456...","amount":[{"denom":"udys","amount":"100"}]}' --attached-message '{"@type":"/cosmos.bank.v1beta1.MsgSend","from_address":"dys2123...","to_address":"dys789...","amount":[{"denom":"udys","amount":"200"}]}'

  # Execute a script with executor address
  $ dysond query script run --script-address dys2123... --executor-address dys456... --args '["data"]'`,
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientQueryContext(cmd)
			if err != nil {
				return fmt.Errorf("failed to get client query context: %w", err)
			}

			queryClient := scripttypes.NewQueryClient(clientCtx)

			scriptAddress, err := cmd.Flags().GetString("script-address")
			if err != nil {
				return fmt.Errorf("failed to get --script-address: %w", err)
			}
			if scriptAddress == "" {
				return errors.New("--script-address flag is required")
			}

			executorAddress, err := cmd.Flags().GetString("executor-address")
			if err != nil {
				return fmt.Errorf("failed to get --executor-address: %w", err)
			}

			inputArgs, err := cmd.Flags().GetString("args")
			if err != nil {
				return fmt.Errorf("failed to get --args: %w", err)
			}

			functionName, err := cmd.Flags().GetString("function-name")
			if err != nil {
				return fmt.Errorf("failed to get --function-name: %w", err)
			}

			// Handle extra-code and extra-code-path flags
			extraCodeProvided := cmd.Flags().Changed("extra-code")
			extraCodePathProvided := cmd.Flags().Changed("extra-code-path")

			// Validate both are not provided
			if extraCodeProvided && extraCodePathProvided {
				return errors.New("cannot provide both --extra-code and --extra-code-path, use only one")
			}

			var extraCode string
			if extraCodeProvided {
				extraCode, err = cmd.Flags().GetString("extra-code")
				if err != nil {
					return fmt.Errorf("failed to get --extra-code: %w", err)
				}
			} else if extraCodePathProvided {
				extraCodePath, err := cmd.Flags().GetString("extra-code-path")
				if err != nil {
					return fmt.Errorf("failed to get --extra-code-path: %w", err)
				}
				// Read file contents
				codeBytes, err := os.ReadFile(extraCodePath)
				if err != nil {
					return fmt.Errorf("failed to read file %s: %w", extraCodePath, err)
				}
				extraCode = string(codeBytes)
			}

			kwargs, err := cmd.Flags().GetString("kwargs")
			if err != nil {
				return fmt.Errorf("failed to get --kwargs: %w", err)
			}

			// Parse attached messages
			attachedMessageStrings, err := cmd.Flags().GetStringArray("attached-message")
			if err != nil {
				return fmt.Errorf("failed to get --attached-message: %w", err)
			}

			var attachedMessages []*types.Any
			for _, msgStr := range attachedMessageStrings {
				if msgStr == "" {
					continue
				}

				// Parse and encode the JSON message properly
				var msg sdk.Msg
				err := clientCtx.Codec.UnmarshalInterfaceJSON([]byte(msgStr), &msg)
				if err != nil {
					return fmt.Errorf("failed to unmarshal attached message JSON: %w", err)
				}

				// Create the Any message with properly encoded protobuf
				anyMsg, err := types.NewAnyWithValue(msg)
				if err != nil {
					return fmt.Errorf("failed to create Any message: %w", err)
				}

				attachedMessages = append(attachedMessages, anyMsg)
			}

			req := &scripttypes.RunScript{
				ScriptAddress:    scriptAddress,
				ExecutorAddress:  executorAddress,
				Args:             inputArgs,
				FunctionName:     functionName,
				ExtraCode:        extraCode,
				Kwargs:           kwargs,
				AttachedMessages: attachedMessages,
			}

			res, err := queryClient.Run(context.Background(), req)
			if err != nil {
				return fmt.Errorf("failed to run script: %w", err)
			}

			return clientCtx.PrintProto(res)
		},
	}

	cmd.Flags().String("script-address", "", "Address of the script to execute (required)")
	cmd.Flags().String("executor-address", "", "Address of the executor account")
	cmd.Flags().String("args", "", "Input data for the script execution as positional arguments (JSON list)")
	cmd.Flags().String("function-name", "", "Name of the function to execute")
	cmd.Flags().String("extra-code", "", "Extra code to temporarily append to the script (only if executor is owner)")
	cmd.Flags().String("extra-code-path", "", "Path to file containing extra code to temporarily append to the script (only if executor is owner)")
	cmd.Flags().String("kwargs", "", "Keyword arguments for the script execution (JSON dictionary)")
	cmd.Flags().StringArray("attached-message", []string{}, "Attached message to include in the transaction as JSON (can be used multiple times)")

	flags.AddQueryFlagsToCmd(cmd)

	return cmd
}

// GetCmdQueryScriptInfo returns the command to query script info
func GetCmdQueryScriptInfo() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "script-info --address <script_address>",
		Short: "Query for script info by address",
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientQueryContext(cmd)
			if err != nil {
				return err
			}

			queryClient := scripttypes.NewQueryClient(clientCtx)

			address, err := cmd.Flags().GetString("address")
			if err != nil {
				return err
			}
			if address == "" {
				return errors.New("--address flag is required")
			}

			req := &scripttypes.QueryScriptInfoRequest{
				Address: address,
			}

			res, err := queryClient.ScriptInfo(context.Background(), req)
			if err != nil {
				return err
			}

			return clientCtx.PrintProto(res)
		},
	}

	cmd.Flags().String("address", "", "Address of the script (required)")

	flags.AddQueryFlagsToCmd(cmd)

	return cmd
}

// GetCmdQueryBenchmark returns the command to run a benchmark
func GetCmdQueryBenchmark() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "benchmark [--iterations <number>] [--details]",
		Short: "Run a benchmark test",
		Long: `Runs a benchmark test using the dyslang virtual machine.

This command executes a performance benchmark to test the dyslang execution environment.

Optional Flags:
  --iterations: Number of iterations for transcendental function tests (default: 100)
  --details: Show detailed benchmark results (default: only total_hash)

Examples:
  $ dysond query script benchmark
  $ dysond query script benchmark --iterations 1000
  $ dysond query script benchmark --details`,
		RunE: func(cmd *cobra.Command, args []string) error {
			iterations, err := cmd.Flags().GetInt("iterations")
			if err != nil {
				return fmt.Errorf("failed to get --iterations: %w", err)
			}

			details, err := cmd.Flags().GetBool("details")
			if err != nil {
				return fmt.Errorf("failed to get --details: %w", err)
			}

			// Call the benchmark function with iterations and details parameters
			output, err := dysvm.Benchmark(context.Background(), iterations, details)
			if err != nil {
				return fmt.Errorf("benchmark failed: %w", err)
			}

			// Print the benchmark results
			fmt.Print(output)
			return nil
		},
	}

	cmd.Flags().Int("iterations", 100, "Number of iterations for transcendental function tests")
	cmd.Flags().Bool("details", false, "Show detailed benchmark results (default: only total_hash)")

	flags.AddQueryFlagsToCmd(cmd)

	return cmd
}
