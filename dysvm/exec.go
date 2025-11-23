package dysvm

import (
	"context"
	"fmt"
	"io"
	"os"
	"strings"

	"dysonprotocol.com/dysvm/internal/data"

	"github.com/kluctl/go-embed-python/embed_util"
	"github.com/kluctl/go-embed-python/python"

	cosmossdkerrors "cosmossdk.io/errors"
)

func Exec(ctx context.Context, msgJSON, scriptJSON, attachedMsgResultsJSON, headerInfoJSON, port string) (string, error) {
	if os.Getenv("DYSLANG_SERVER") == "1" {
		// Route through long-running server
		return getServer(ctx).Exec(ctx, msgJSON, scriptJSON, attachedMsgResultsJSON, headerInfoJSON, port)
	}
	var lib *embed_util.EmbeddedFiles
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded python")
	}

	lib, err = embed_util.NewEmbeddedFiles(data.Data, "dyslang-libs")

	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded files")
	}
	// TODO Make this an environment variable or config
	ep.AddPythonPath("./dysvm/internal/py-dyslang")
	ep.AddPythonPath(lib.GetExtractedPath())

	cmd, err := ep.PythonCmd("-m", "dyslang", "exec_script", msgJSON, scriptJSON, attachedMsgResultsJSON, headerInfoJSON, port)

	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to run exec")
	}

	out, runErr := cmd.CombinedOutput()

	return string(out), runErr

}

func Benchmark(ctx context.Context, iterations int, details bool) (string, error) {
	if os.Getenv("DYSLANG_SERVER") == "1" {
		return getServer(ctx).Benchmark(ctx, iterations, details)
	}
	var lib *embed_util.EmbeddedFiles
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded python")
	}

	lib, err = embed_util.NewEmbeddedFiles(data.Data, "dyslang-libs")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded files")
	}

	// TODO Make this an environment variable or config
	ep.AddPythonPath("./dysvm/internal/py-dyslang")
	ep.AddPythonPath(lib.GetExtractedPath())

	var detailsFlag string
	if details {
		detailsFlag = "true"
	} else {
		detailsFlag = "false"
	}

	cmd, err := ep.PythonCmd("-m", "dyslang", "run_benchmark", fmt.Sprintf("%d", iterations), detailsFlag)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to run benchmark")
	}

	out, runErr := cmd.CombinedOutput()

	return string(out), runErr
}

func Wsgi(ctx context.Context, port, scriptName, scriptJSON, blockInfoJSON, httpreq string) (string, error) {
	if os.Getenv("DYSLANG_SERVER") == "1" {
		return getServer(ctx).Wsgi(ctx, port, scriptName, scriptJSON, blockInfoJSON, httpreq)
	}
	var lib *embed_util.EmbeddedFiles
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded python")
	}

	lib, err = embed_util.NewEmbeddedFiles(data.Data, "dyslang-libs")

	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded files")
	}
	// TODO Make this an environment variable or config
	ep.AddPythonPath("./dysvm/internal/py-dyslang")
	ep.AddPythonPath(lib.GetExtractedPath())

	cmd, err := ep.PythonCmd("-m", "dyslang", "run_wsgi", port, scriptName, scriptJSON, blockInfoJSON, httpreq)

	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to run wsgi")
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to capture wsgi stdout")
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to capture wsgi stderr")
	}

	if err := cmd.Start(); err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to start wsgi process")
	}

	stdoutBytes, stdoutErr := io.ReadAll(stdout)
	stderrBytes, stderrErr := io.ReadAll(stderr)

	if stdoutErr != nil {
		return "", cosmossdkerrors.Wrapf(stdoutErr, "failed to read wsgi stdout")
	}
	if stderrErr != nil {
		return "", cosmossdkerrors.Wrapf(stderrErr, "failed to read wsgi stderr")
	}

	if err := cmd.Wait(); err != nil {
		return "", fmt.Errorf("failed to run wsgi: %w, stderr=%s", err, string(stderrBytes))
	}

	body, logs, err := decodeWsgiResponse(stdoutBytes)
	if err != nil {
		return "", fmt.Errorf("failed to parse wsgi response: %w, stdout=%s, stderr=%s", err, string(stdoutBytes), string(stderrBytes))
	}
	if logs != "" {
		fmt.Print(logs)
	}

	return string(body), nil

}

func DysFormat(ctx context.Context, code string) (string, error) {
	if os.Getenv("DYSLANG_SERVER") == "1" {
		return getServer(ctx).DysFormat(ctx, code)
	}
	var lib *embed_util.EmbeddedFiles
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to dys format")
	}

	lib, err = embed_util.NewEmbeddedFiles(data.Data, "dyslang-libs")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded files")
	}

	// TODO Make this an environment variable or config
	ep.AddPythonPath("./dysvm/internal/py-dyslang")
	ep.AddPythonPath(lib.GetExtractedPath())

	cmd, err := ep.PythonCmd("-m", "dyslang", "dys_format")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to dys format")
	}

	// Set stdin to the code
	cmd.Stdin = strings.NewReader(code)

	out, runErr := cmd.Output()
	if runErr != nil {
		return "", fmt.Errorf("failed to format code: %w, %s", runErr, string(out))
	}

	return string(out), nil
}

func ExtractFunctionSchema(ctx context.Context, scriptJSON, blockInfoJSON, port, executorAddress, scriptName string) (string, error) {
	if os.Getenv("DYSLANG_SERVER") == "1" {
		return getServer(ctx).ExtractFunctionSchema(ctx, scriptJSON, blockInfoJSON, port, executorAddress, scriptName)
	}
	var lib *embed_util.EmbeddedFiles
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded python")
	}

	lib, err = embed_util.NewEmbeddedFiles(data.Data, "dyslang-libs")
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to create embedded files")
	}

	// TODO Make this an environment variable or config
	ep.AddPythonPath("./dysvm/internal/py-dyslang")
	ep.AddPythonPath(lib.GetExtractedPath())

	cmd, err := ep.PythonCmd("-m", "dyslang", "extract_function_schema", scriptJSON, blockInfoJSON, port, executorAddress, scriptName)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to dys format")
	}

	out, runErr := cmd.CombinedOutput()
	return string(out), runErr
}
