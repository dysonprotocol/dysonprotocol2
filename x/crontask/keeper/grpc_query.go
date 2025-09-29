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

// TaskByID returns a task by its ID
func (q queryServer) TaskByID(ctx context.Context, req *crontasktypes.QueryTaskByIDRequest) (*crontasktypes.QueryTaskByIDResponse, error) {
	task, err := q.k.GetTask(ctx, req.TaskId)
	if err != nil {
		return nil, status.Error(codes.NotFound, fmt.Sprintf("task with ID %d not found", req.TaskId))
	}
	return &crontasktypes.QueryTaskByIDResponse{Task: &task}, nil
}

// TasksByAddress returns all tasks created by a specific address
func (q queryServer) TasksByAddress(ctx context.Context, req *crontasktypes.QueryTasksByAddressRequest) (*crontasktypes.QueryTasksResponse, error) {
	store := prefix.NewStore(q.k.kvStore(ctx), append(indexAddrPrefix, []byte(req.Creator)...))

	tasks := make([]*crontasktypes.Task, 0)
	pageRes, err := query.Paginate(store, req.Pagination, func(key, _ []byte) error {
		id := binary.BigEndian.Uint64(key[len(key)-8:])
		task, err := q.k.GetTask(ctx, id)
		if err != nil {
			return err
		}
		tasks = append(tasks, &task)
		return nil
	})
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &crontasktypes.QueryTasksResponse{Tasks: tasks, Pagination: pageRes}, nil
}

// TasksByStatusTimestamp returns tasks filtered by status and ordered by timestamp
func (q queryServer) TasksByStatusTimestamp(ctx context.Context, req *crontasktypes.QueryTasksByStatusTimestampRequest) (*crontasktypes.QueryTasksResponse, error) {
	if req.Pagination == nil {
		req.Pagination = &query.PageRequest{}
	}

	// invert the pagination
	req.Pagination.Reverse = !req.Pagination.Reverse

	prefixBz := append(indexStatusTsPrefix, []byte(req.Status)...)
	store := prefix.NewStore(q.k.kvStore(ctx), prefixBz)

	tasks := make([]*crontasktypes.Task, 0)
	pageRes, err := query.Paginate(store, req.Pagination, func(key, _ []byte) error {
		id := binary.BigEndian.Uint64(key[len(key)-8:])
		task, err := q.k.GetTask(ctx, id)
		if err != nil {
			// Return the error instead of silently skipping the task
			return err
		}
		tasks = append(tasks, &task)
		return nil
	})
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to get tasks by status timestamp")
	}

	return &crontasktypes.QueryTasksResponse{Tasks: tasks, Pagination: pageRes}, nil
}

// TasksByStatusGasPrice returns tasks filtered by status and ordered by gas price
func (q queryServer) TasksByStatusGasPrice(ctx context.Context, req *crontasktypes.QueryTasksByStatusGasPriceRequest) (*crontasktypes.QueryTasksResponse, error) {
	if req.Pagination == nil {
		req.Pagination = &query.PageRequest{}
	}
	// invert the pagination
	req.Pagination.Reverse = !req.Pagination.Reverse

	prefixBz := append(indexStatusGasPrefix, []byte(req.Status)...)
	store := prefix.NewStore(q.k.kvStore(ctx), prefixBz)

	tasks := make([]*crontasktypes.Task, 0)
	pageRes, err := query.Paginate(store, req.Pagination, func(key, _ []byte) error {
		id := binary.BigEndian.Uint64(key[len(key)-8:])
		task, err := q.k.GetTask(ctx, id)
		if err != nil {
			// Return the error instead of silently skipping the task
			return err
		}
		tasks = append(tasks, &task)
		return nil
	})
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to get tasks by status gas price")
	}

	return &crontasktypes.QueryTasksResponse{Tasks: tasks, Pagination: pageRes}, nil
}

// TasksAll returns all tasks ordered by task ID (ascending)
func (q queryServer) TasksAll(ctx context.Context, req *crontasktypes.QueryAllTasksRequest) (*crontasktypes.QueryTasksResponse, error) {
	// The `Tasks` collection is stored under a single-byte prefix 0 (see keeper.TasksKey).
	// We create a prefixed store so that Paginate only iterates over task entries.
	store := prefix.NewStore(q.k.kvStore(ctx), []byte{0})

	tasks := make([]*crontasktypes.Task, 0)
	pageRes, err := query.Paginate(store, req.Pagination, func(key, _ []byte) error {
		// The key layout is: <prefix byte><8-byte big-endian taskID>
		if len(key) < 8 {
			return nil
		}
		id := binary.BigEndian.Uint64(key[len(key)-8:])
		task, err := q.k.GetTask(ctx, id)
		if err != nil {
			// Return the error instead of silently skipping the task
			return err
		}
		tasks = append(tasks, &task)
		return nil
	})
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to get tasks all")
	}

	return &crontasktypes.QueryTasksResponse{Tasks: tasks, Pagination: pageRes}, nil
}

// Metrics returns the last-block crontask metrics singleton
func (q queryServer) Metrics(ctx context.Context, req *crontasktypes.QueryMetricsRequest) (*crontasktypes.QueryMetricsResponse, error) {
	metrics, err := q.k.GetMetrics(ctx)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to get metrics")
	}
	return &crontasktypes.QueryMetricsResponse{Metrics: &metrics}, nil
}

// EventSubscriptionByID returns a subscription by id
func (q queryServer) SubscriptionByID(ctx context.Context, req *crontasktypes.QuerySubscriptionByIDRequest) (*crontasktypes.QuerySubscriptionByIDResponse, error) {
	sub, err := q.k.Subscriptions.Get(ctx, req.SubscriptionId)
	if err != nil {
		return nil, status.Error(codes.NotFound, "subscription not found")
	}
	return &crontasktypes.QuerySubscriptionByIDResponse{Subscription: &sub}, nil
}

// EventSubscriptionsByCreator returns subscriptions filtered by creator
func (q queryServer) SubscriptionsByCreator(ctx context.Context, req *crontasktypes.QuerySubscriptionsByCreatorRequest) (*crontasktypes.QuerySubscriptionsResponse, error) {
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

	return &crontasktypes.QuerySubscriptionsResponse{
		Subscriptions: subs,
		Pagination:    pageRes,
	}, nil
}

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

// Params returns the module parameters
func (q queryServer) Params(ctx context.Context, req *crontasktypes.QueryParamsRequest) (*crontasktypes.QueryParamsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	params := q.k.GetParams(ctx)
	return &crontasktypes.QueryParamsResponse{Params: &params}, nil
}

// QueryParams was the old name - keeping it for compatibility but making it call the new method
func (k Keeper) QueryParams(ctx context.Context, req *crontasktypes.QueryParamsRequest) (*crontasktypes.QueryParamsResponse, error) {
	// Create a queryServer and delegate to it
	q := queryServer{k: k}
	return q.Params(ctx, req)
}

// Note: SubscriptionsByStatus RPC is not currently defined in the proto. If needed,
// add it to `proto/dysonprotocol/crontask/v1/query.proto` before reintroducing here.
