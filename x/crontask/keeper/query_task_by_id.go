package keeper

import (
	"context"
	"fmt"

	crontasktypes "dysonprotocol.com/x/crontask/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// TaskByID returns a task by its ID
func (q queryServer) TaskByID(ctx context.Context, req *crontasktypes.QueryTaskByIDRequest) (*crontasktypes.QueryTaskByIDResponse, error) {
	task, err := q.k.GetTask(ctx, req.TaskId)
	if err != nil {
		return nil, status.Error(codes.NotFound, fmt.Sprintf("task with ID %d not found", req.TaskId))
	}
	return &crontasktypes.QueryTaskByIDResponse{Task: &task}, nil
}
