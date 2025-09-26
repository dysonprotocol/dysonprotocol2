package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
)

func (k Keeper) Params(ctx context.Context, _ *whaleswapv1.QueryParamsRequest) (*whaleswapv1.QueryParamsResponse, error) {
	p := k.GetParams(ctx)
	return &whaleswapv1.QueryParamsResponse{Params: p}, nil
}

func (k Keeper) Pool(ctx context.Context, req *whaleswapv1.QueryPoolRequest) (*whaleswapv1.QueryPoolResponse, error) {
	if req == nil || req.PoolId == 0 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "pool_id required")
	}
	p, err := k.PoolsMap.Get(ctx, req.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool not found: %d", req.PoolId)
	}
	return &whaleswapv1.QueryPoolResponse{Pool: &p}, nil
}

func (k Keeper) Pools(ctx context.Context, req *whaleswapv1.QueryPoolsRequest) (*whaleswapv1.QueryPoolsResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryPoolsRequest{}
	}
	results, pageRes, err := query.CollectionPaginate(ctx, k.PoolsMap, req.Pagination, func(key uint64, value whaleswapv1.Pool) (*whaleswapv1.Pool, error) {
		v := value
		return &v, nil
	})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate pools failed")
	}
	return &whaleswapv1.QueryPoolsResponse{Pools: results, Pagination: pageRes}, nil
}
