package keeper

import (
	"context"
	"encoding/binary"
	"fmt"

	errorsmod "cosmossdk.io/errors"
	"cosmossdk.io/store/prefix"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// isValidStatus checks if the provided status is a valid task status
func isValidStatus(status string) bool {
	validStatuses := []string{
		crontasktypes.TaskStatus_SCHEDULED,
		crontasktypes.TaskStatus_PENDING,
		crontasktypes.TaskStatus_DONE,
		crontasktypes.TaskStatus_FAILED,
		crontasktypes.TaskStatus_EXPIRED,
	}

	for _, s := range validStatuses {
		if s == status {
			return true
		}
	}
	return false
}

// Ensure the queryServer implements the QueryServer interface
var _ crontasktypes.QueryServer = queryServer{}

// queryServer is a wrapper for Keeper that implements the QueryServer interface
type queryServer struct {
	k Keeper
}

// NewQueryServer creates a new QueryServer instance
func NewQueryServer(k Keeper) crontasktypes.QueryServer {
	return queryServer{k: k}
}

// QueryParams was the old name - keeping it for compatibility but making it call the new method
func (k Keeper) QueryParams(ctx context.Context, req *crontasktypes.QueryParamsRequest) (*crontasktypes.QueryParamsResponse, error) {
	// Create a queryServer and delegate to it
	q := queryServer{k: k}
	return q.Params(ctx, req)
}

// Note: SubscriptionsByStatus RPC is not currently defined in the proto. If needed,
// add it to `proto/dysonprotocol/crontask/v1/query.proto` before reintroducing here.
