package keeper

import (
	"context"
	"encoding/binary"

	"cosmossdk.io/store/prefix"
	crontasktypes "dysonprotocol.com/x/crontask/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// TasksByAddress returns all tasks created by a specific address
func (q queryServer) TasksByAddress(ctx context.Context, req *crontasktypes.QueryTasksByAddressRequest) (*crontasktypes.QueryTasksByAddressResponse, error) {
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

	return &crontasktypes.QueryTasksByAddressResponse{Tasks: tasks, Pagination: pageRes}, nil
}
