package keeper

import (
	"context"
	"encoding/binary"

	errorsmod "cosmossdk.io/errors"
	"cosmossdk.io/store/prefix"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

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
