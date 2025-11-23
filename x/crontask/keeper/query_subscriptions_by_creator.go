package keeper

import (
	"context"

	errorsmod "cosmossdk.io/errors"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// EventSubscriptionsByCreator returns subscriptions filtered by creator
func (q queryServer) SubscriptionsByCreator(ctx context.Context, req *crontasktypes.QuerySubscriptionsByCreatorRequest) (*crontasktypes.QuerySubscriptionsByCreatorResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	// Use CollectionFilteredPaginate over the primary subscriptions collection and filter by creator.
	subs, pageRes, err := query.CollectionFilteredPaginate(
		ctx,
		q.k.Subscriptions,
		req.Pagination,
		func(_ uint64, sub crontasktypes.Subscription) (bool, error) {
			return sub.Creator == req.Creator, nil
		},
		func(_ uint64, sub crontasktypes.Subscription) (*crontasktypes.Subscription, error) {
			copy := sub
			return &copy, nil
		},
	)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to paginate subscriptions by creator")
	}

	return &crontasktypes.QuerySubscriptionsByCreatorResponse{
		Subscriptions: subs,
		Pagination:    pageRes,
	}, nil
}
