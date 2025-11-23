package keeper

import (
	"context"

	crontasktypes "dysonprotocol.com/x/crontask/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// EventSubscriptionByID returns a subscription by id
func (q queryServer) SubscriptionByID(ctx context.Context, req *crontasktypes.QuerySubscriptionByIDRequest) (*crontasktypes.QuerySubscriptionByIDResponse, error) {
	sub, err := q.k.Subscriptions.Get(ctx, req.SubscriptionId)
	if err != nil {
		return nil, status.Error(codes.NotFound, "subscription not found")
	}
	return &crontasktypes.QuerySubscriptionByIDResponse{Subscription: &sub}, nil
}
