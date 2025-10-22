package keeper

import (
	"context"
	"fmt"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

func (k Keeper) TradesByOffer(ctx context.Context, req *whaleswapv1.QueryTradesByOfferRequest) (*whaleswapv1.QueryTradesByOfferResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByOfferRequest{}
	}
	if req.OfferId == 0 {
		return nil, fmt.Errorf("offer_id required")
	}
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByOfferIndex,
		req.Pagination,
		func(key collections.Pair[uint64, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != req.OfferId {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		query.WithCollectionPaginationPairPrefix[uint64, uint64](req.OfferId),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by offer failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByOfferResponse{Trades: trades, Pagination: pageRes}, nil
}

func (k Keeper) TradesByTaker(ctx context.Context, req *whaleswapv1.QueryTradesByTakerRequest) (*whaleswapv1.QueryTradesByTakerResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByTakerRequest{}
	}
	if req.Taker == "" {
		return nil, fmt.Errorf("taker required")
	}
	trader := req.Taker
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByTraderIndex,
		req.Pagination,
		func(key collections.Pair[string, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != trader {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		query.WithCollectionPaginationPairPrefix[string, uint64](trader),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by trader failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByTakerResponse{Trades: trades, Pagination: pageRes}, nil
}

func (k Keeper) TradesByPool(ctx context.Context, req *whaleswapv1.QueryTradesByPoolRequest) (*whaleswapv1.QueryTradesByPoolResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByPoolRequest{}
	}
	if req.PoolId == 0 {
		return nil, fmt.Errorf("pool_id required")
	}
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByPoolIndex,
		req.Pagination,
		func(key collections.Pair[uint64, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != req.PoolId {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		// Iterate only keys with pool_id prefix to avoid scanning unrelated pairs and to
		// ensure next_key encodes a valid pair key for subsequent pages.
		query.WithCollectionPaginationPairPrefix[uint64, uint64](req.PoolId),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by pool failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByPoolResponse{Trades: trades, Pagination: pageRes}, nil
}

func (k Keeper) Trades(ctx context.Context, req *whaleswapv1.QueryTradesRequest) (*whaleswapv1.QueryTradesResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesRequest{}
	}
	sentDenom := req.SentDenom
	receivedDenom := req.ReceivedDenom
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		k.TradesMap,
		req.Pagination,
		func(_ uint64, value whaleswapv1.Trade) (bool, error) {
			if sentDenom != "" && value.TotalSent.AmountOf(sentDenom).IsZero() {
				return false, nil
			}
			if receivedDenom != "" && value.TotalReceived.AmountOf(receivedDenom).IsZero() {
				return false, nil
			}
			return true, nil
		},
		func(_ uint64, value whaleswapv1.Trade) (*whaleswapv1.Trade, error) {
			v := value
			return &v, nil
		},
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesResponse{Trades: trades, Pagination: pageRes}, nil
}

func (k Keeper) TradesByAuction(ctx context.Context, req *whaleswapv1.QueryTradesByAuctionRequest) (*whaleswapv1.QueryTradesByAuctionResponse, error) {
	if req == nil {
		req = &whaleswapv1.QueryTradesByAuctionRequest{}
	}
	if req.AuctionId == 0 {
		return nil, fmt.Errorf("auction_id required")
	}
	var trades []*whaleswapv1.Trade
	results, pageRes, err := query.CollectionPaginate(
		ctx,
		k.TradesByAuctionIndex,
		req.Pagination,
		func(key collections.Pair[uint64, uint64], id uint64) (*whaleswapv1.Trade, error) {
			k1, _ := key.K1(), key.K2()
			if k1 != req.AuctionId {
				return nil, nil
			}
			v, err := k.TradesMap.Get(ctx, id)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", id)
			}
			vv := v
			return &vv, nil
		},
		query.WithCollectionPaginationPairPrefix[uint64, uint64](req.AuctionId),
	)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "paginate trades by auction failed")
	}
	trades = results
	return &whaleswapv1.QueryTradesByAuctionResponse{Trades: trades, Pagination: pageRes}, nil
}

func (k Keeper) Trade(ctx context.Context, req *whaleswapv1.QueryTradeRequest) (*whaleswapv1.QueryTradeResponse, error) {
	if req == nil || req.TradeId == 0 {
		return nil, fmt.Errorf("trade_id required")
	}
	v, err := k.TradesMap.Get(ctx, req.TradeId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "trade not found: %d", req.TradeId)
	}
	vv := v
	return &whaleswapv1.QueryTradeResponse{Trade: &vv}, nil
}
