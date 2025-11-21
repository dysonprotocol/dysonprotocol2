package keeper

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"strconv"
	"time"

	"cosmossdk.io/core/header"
	cosmossdkerrors "cosmossdk.io/errors"
	"dysonprotocol.com/dysvm"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"

	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/gorilla/mux"
	"github.com/gorilla/rpc"
	rpcjson "github.com/gorilla/rpc/json"
)

type RpcService struct {
	k             *Keeper
	ctx           sdk.Context
	ScriptAddress sdk.AccAddress
	App           *baseapp.BaseApp
}

func (k Keeper) NewRPCServer(ctx sdk.Context, address string, app *baseapp.BaseApp) (string, *http.Server, error) {
	s := rpc.NewServer()
	s.RegisterCodec(rpcjson.NewCodec(), "application/json")
	s.RegisterCodec(rpcjson.NewCodec(), "application/json;charset=UTF-8")
	rpcservice := new(RpcService)
	rpcservice.k = &k
	rpcservice.ctx = ctx
	addr, err := k.addressCodec.StringToBytes(address)

	if err != nil {
		return "", nil, err
	}
	rpcservice.ScriptAddress = addr
	rpcservice.App = app

	s.RegisterService(rpcservice, "")
	r := mux.NewRouter()
	r.Handle("/rpc", s)
	srv := &http.Server{Handler: r}

	listener, err := net.Listen("tcp", "localhost:0")
	if err != nil {
		panic(err)
	}

	//fmt.Println("Using port:", listener.Addr().(*net.TCPAddr).Port)

	go func() {
		//fmt.Println("start ListenAndServe")
		srv.Serve(listener)
		//fmt.Println("end ListenAndServe")
	}()
	//fmt.Println("running dysvm")
	port := strconv.Itoa(listener.Addr().(*net.TCPAddr).Port)
	return port, srv, nil
}

func (k Keeper) RunWeb(ctx context.Context, scriptAddress string, scriptName string, httpreq string) (string, error) {
	now := time.Now()
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	// Base gas cost for runweb execution
	sdkCtx.GasMeter().ConsumeGas(1_000_000, "script runweb base cost")

	cacheCtx, _ := sdkCtx.CacheContext()

	// Validate input: at least one field must be provided
	if scriptAddress == "" && scriptName == "" {
		return "", cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "either script_address or script_name must be provided")
	}

	var resolvedAddress, name string

	if scriptAddress != "" && scriptName != "" {
		// Both provided: validate that name resolves to the address
		nameResolvedAddress, err := k.NameserviceKeeper.ResolveNameOrAddress(cacheCtx, scriptName)
		if err != nil {
			return "", cosmossdkerrors.Wrapf(err, "failed to resolve script name: %s", scriptName)
		}
		if nameResolvedAddress != scriptAddress {
			return "", cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "script name %s resolves to %s but script address %s was provided", scriptName, nameResolvedAddress, scriptAddress)
		}
		resolvedAddress = scriptAddress
		name = scriptName
	} else if scriptName != "" {
		// Only name provided: resolve to address
		var err error
		resolvedAddress, err = k.NameserviceKeeper.ResolveNameOrAddress(cacheCtx, scriptName)
		if err != nil {
			return "", cosmossdkerrors.Wrapf(err, "failed to resolve script name: %s", scriptName)
		}
		name = scriptName
	} else {
		// Only address provided: use it directly
		resolvedAddress = scriptAddress
	}

	var script scripttypes.Script
	exists, err := k.ScriptMap.Has(cacheCtx, resolvedAddress)
	if err != nil {
		return "", cosmossdkerrors.Wrap(err, "failed to check script existence")
	}
	if !exists {
		script = scripttypes.Script{
			Address: resolvedAddress,
			Version: 0,
			Code:    "",
		}
	} else {
		script, err = k.ScriptMap.Get(cacheCtx, resolvedAddress)
		if err != nil {
			return "", cosmossdkerrors.Wrap(err, "failed to get script")
		}
	}

	scriptJSON, err := k.cdc.MarshalInterfaceJSON(&script)
	if err != nil {
		return "", err
	}
	headerInfo := header.Info{
		Height:  cacheCtx.BlockHeight(),
		Time:    cacheCtx.BlockTime(),
		ChainID: cacheCtx.ChainID(),
		AppHash: cacheCtx.BlockHeader().AppHash,
		Hash:    cacheCtx.BlockHeader().LastBlockId.Hash,
	}

	headerInfoJSON, err := json.Marshal(headerInfo)
	if err != nil {
		return "", err
	}

	// For RunWeb, initialize depth if not present (similar to execScript)
	depth, ok := cacheCtx.Value(scriptDepthKey{}).(int)
	if !ok {
		depth = 1
	} else {
		depth++
	}
	depthCtx := cacheCtx.WithValue(scriptDepthKey{}, depth)

	port, srv, err := k.NewRPCServer(depthCtx, script.Address, k.App)

	if err != nil {
		return "", err
	}
	defer func() {
		k.Logger(depthCtx).Info("Elapsed time", "time", time.Since(now))

		if err := srv.Shutdown(context.Background()); err != nil {
			k.Logger(depthCtx).Error("shutdown error", "error", err)
			panic(err) // failure/timeout shutting down the server gracefully
		}
	}()

	out, err := dysvm.Wsgi(ctx, port, name, string(scriptJSON), string(headerInfoJSON), httpreq)

	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "error running script: %s", string(out))
	}

	return out, nil
}
