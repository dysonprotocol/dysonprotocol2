package types

import (
	sdkerrors "cosmossdk.io/errors"
)

// x/whaleswap module sentinel errors
var (
	ErrUnimplemented    = sdkerrors.Register("whaleswap", 1, "unimplemented")
	ErrInvalidAuthority = sdkerrors.Register("whaleswap", 2, "invalid authority")
	// Leverage errors
	ErrBorrowCapExceeded         = sdkerrors.Register("whaleswap", 1001, "borrow cap exceeded")
	ErrInsufficientCollateral    = sdkerrors.Register("whaleswap", 1002, "insufficient collateral")
	ErrPositionNotLiquidatable   = sdkerrors.Register("whaleswap", 1003, "position not liquidatable")
	ErrBlockDelayNotPassed       = sdkerrors.Register("whaleswap", 1004, "block delay not passed")
	ErrInvalidCollateralRatio    = sdkerrors.Register("whaleswap", 1005, "invalid collateral ratio")
	ErrLiquidationAlreadyPending = sdkerrors.Register("whaleswap", 1006, "liquidation already pending")
	ErrLeverageDisabled          = sdkerrors.Register("whaleswap", 1007, "leverage disabled for denom")
)
