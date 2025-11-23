package keeper

import (
	"context"
	"encoding/binary"

	errorsmod "cosmossdk.io/errors"
	"cosmossdk.io/store/prefix"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/types/query"
)

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
