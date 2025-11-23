package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// EventSubscriptionsAll returns all subscriptions
func (q queryServer) SubscriptionsAll(ctx context.Context, req *crontasktypes.QuerySubscriptionsAllRequest) (*crontasktypes.QuerySubscriptionsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	subs, pageRes, err := query.CollectionPaginate(
		ctx,
		q.k.Subscriptions,
		req.Pagination,
		func(_ uint64, sub crontasktypes.Subscription) (*crontasktypes.Subscription, error) {
			subCopy := sub
			return &subCopy, nil
		},
	)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to paginate subscriptions")
	}

	return &crontasktypes.QuerySubscriptionsResponse{Subscriptions: subs, Pagination: pageRes}, nil
}
