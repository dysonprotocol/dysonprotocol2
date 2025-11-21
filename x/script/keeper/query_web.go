package keeper

import (
	"context"

	scripttypes "dysonprotocol.com/x/script/types"
)

// Web queries the WSGI web application function of a script. This is used in the REST API and
// is not likely needed to use directly.
//
// Semantics:
//   - Delegates to RunWeb which handles script resolution and execution.
//   - Executes script's WSGI application in read-only mode.
//   - Returns HTTP response from the script's web application.
//   - No state changes are allowed in web requests.
//
// Validation:
//   - Either script_address or script_name must be provided.
//   - Script must exist and have a valid WSGI application.
//   - HTTP request must be valid.
//
// Returns:
//   - *scripttypes.WebResponse with HTTP response from the script.
//
// Errors are returned on script resolution failures, execution errors, or invalid requests; no panics.
func (k Keeper) Web(ctx context.Context, req *scripttypes.WebRequest) (*scripttypes.WebResponse, error) {
	// Calls RunWeb which handles name resolution via nameservice keeper
	out, err := k.RunWeb(ctx, req.ScriptAddress, req.ScriptName, req.Httprequest)
	if err != nil {
		return nil, err
	}

	return &scripttypes.WebResponse{
		Httpresponse: out,
	}, nil
}
