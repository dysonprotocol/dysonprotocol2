package dysonprotocol

import (
	"context"
	"errors"
	"strings"

	"cosmossdk.io/core/address"
	errorsmod "cosmossdk.io/errors"
	txsigning "cosmossdk.io/x/tx/signing"

	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/x/auth/ante"
	authsigning "github.com/cosmos/cosmos-sdk/x/auth/signing"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	"google.golang.org/protobuf/types/known/anypb"
)

// HandlerOptions are the options required for constructing a default SDK AnteHandler.
type HandlerOptions struct {
	ante.HandlerOptions
}

// AutoCreateAccountKeeper wraps an AccountKeeper and automatically creates accounts
// when they don't exist during GetAccount calls. This eliminates the need for
// offline signing and account number prediction for new accounts.
type AutoCreateAccountKeeper struct {
	ante.AccountKeeper
	addressCodec address.Codec
	// Track accounts created in the current transaction
	newlyCreatedAccounts map[string]bool
}

// AccountKeeperI defines the extended interface needed for account creation
type AccountKeeperI interface {
	ante.AccountKeeper
	HasAccount(ctx context.Context, addr sdk.AccAddress) bool
	NewAccountWithAddress(ctx context.Context, addr sdk.AccAddress) sdk.AccountI
	AddressCodec() address.Codec
}

// NewAutoCreateAccountKeeper creates a new AutoCreateAccountKeeper
func NewAutoCreateAccountKeeper(ak ante.AccountKeeper) (*AutoCreateAccountKeeper, error) {
	extendedAK, ok := ak.(AccountKeeperI)
	if !ok {
		return nil, errors.New("account keeper does not implement required interface for auto account creation")
	}

	return &AutoCreateAccountKeeper{
		AccountKeeper:        ak,
		addressCodec:         extendedAK.AddressCodec(),
		newlyCreatedAccounts: make(map[string]bool),
	}, nil
}

// GetAccount wraps the underlying GetAccount and creates the account if it doesn't exist
func (acak *AutoCreateAccountKeeper) GetAccount(ctx context.Context, addr sdk.AccAddress) sdk.AccountI {
	// Try to get the account normally first
	acc := acak.AccountKeeper.GetAccount(ctx, addr)
	if acc != nil {
		return acc
	}

	// Account doesn't exist, create it automatically
	extendedAK, ok := acak.AccountKeeper.(AccountKeeperI)
	if !ok {
		// Fallback to normal behavior if cast fails
		return nil
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	addrStr, err := acak.addressCodec.BytesToString(addr)
	if err != nil {
		sdkCtx.Logger().Error("failed to convert address to string for auto account creation",
			"error", err)
		return nil
	}

	sdkCtx.Logger().Info("automatically creating account during lookup",
		"address", addrStr)

	// Create new account
	newAccount := extendedAK.NewAccountWithAddress(ctx, addr)
	if newAccount == nil {
		sdkCtx.Logger().Error("failed to create new account during auto-creation",
			"address", addrStr)
		return nil
	}

	// Store the account
	extendedAK.SetAccount(ctx, newAccount)

	// Mark as newly created in this transaction
	acak.newlyCreatedAccounts[addrStr] = true

	sdkCtx.Logger().Info("successfully auto-created account",
		"address", addrStr,
		"account_number", newAccount.GetAccountNumber())

	return newAccount
}

// IsNewlyCreated returns true if the account was created in this transaction
func (acak *AutoCreateAccountKeeper) IsNewlyCreated(addr sdk.AccAddress) bool {
	addrStr, err := acak.addressCodec.BytesToString(addr)
	if err != nil {
		return false
	}
	return acak.newlyCreatedAccounts[addrStr]
}

// ResetNewlyCreatedTracking clears the newly created accounts map for a new transaction
func (acak *AutoCreateAccountKeeper) ResetNewlyCreatedTracking() {
	acak.newlyCreatedAccounts = make(map[string]bool)
}

// ConditionalDeductFeeDecorator wraps the standard DeductFeeDecorator
// and only applies fee deduction when fees are non-zero
type ConditionalDeductFeeDecorator struct {
	deductFeeDecorator ante.DeductFeeDecorator
}

// NewConditionalDeductFeeDecorator creates a new ConditionalDeductFeeDecorator
func NewConditionalDeductFeeDecorator(ak ante.AccountKeeper, bk authtypes.BankKeeper, fk ante.FeegrantKeeper, tfc ante.TxFeeChecker) ConditionalDeductFeeDecorator {
	return ConditionalDeductFeeDecorator{
		deductFeeDecorator: ante.NewDeductFeeDecorator(ak, bk, fk, tfc),
	}
}

// AnteHandle implements the AnteDecorator interface
func (cfdd ConditionalDeductFeeDecorator) AnteHandle(ctx sdk.Context, tx sdk.Tx, simulate bool, next sdk.AnteHandler) (sdk.Context, error) {
	feeTx, ok := tx.(sdk.FeeTx)
	if !ok {
		return ctx, errorsmod.Wrap(sdkerrors.ErrTxDecode, "Tx must be a FeeTx")
	}

	// If fees are zero, skip fee deduction and go to next handler
	if feeTx.GetFee().IsZero() {
		return next(ctx, tx, simulate)
	}

	// If fees are non-zero, apply the standard fee deduction logic
	return cfdd.deductFeeDecorator.AnteHandle(ctx, tx, simulate, next)
}

// ZeroSequenceCreateAccountDecorator creates accounts for signers that don't exist
// when the transaction has sequence 0, eliminating the client-side race condition
type ZeroSequenceCreateAccountDecorator struct {
	ak ante.AccountKeeper
}

// NewZeroSequenceCreateAccountDecorator creates a new ZeroSequenceCreateAccountDecorator
func NewZeroSequenceCreateAccountDecorator(ak ante.AccountKeeper) ZeroSequenceCreateAccountDecorator {
	return ZeroSequenceCreateAccountDecorator{
		ak: ak,
	}
}

// AnteHandle implements the AnteDecorator interface
func (zscad ZeroSequenceCreateAccountDecorator) AnteHandle(ctx sdk.Context, tx sdk.Tx, simulate bool, next sdk.AnteHandler) (sdk.Context, error) {
	// Reset newly created tracking for each transaction if using AutoCreateAccountKeeper
	if acak, ok := zscad.ak.(*AutoCreateAccountKeeper); ok {
		acak.ResetNewlyCreatedTracking()
	}

	sigTx, ok := tx.(authsigning.SigVerifiableTx)
	if !ok {
		return ctx, errorsmod.Wrap(sdkerrors.ErrTxDecode, "invalid transaction type")
	}

	// Handle unordered transactions
	utx, ok := tx.(sdk.TxWithUnordered)
	isUnordered := ok && utx.GetUnordered()

	// Get signers
	signers, err := sigTx.GetSigners()
	if err != nil {
		return ctx, errorsmod.Wrap(sdkerrors.ErrTxDecode, "failed to get signers")
	}

	// Get signatures to check sequence numbers
	sigs, err := sigTx.GetSignaturesV2()
	if err != nil {
		return ctx, errorsmod.Wrap(sdkerrors.ErrTxDecode, "failed to get signatures")
	}

	// Validate signer/signature count match
	if len(sigs) != len(signers) {
		return ctx, errorsmod.Wrapf(sdkerrors.ErrUnauthorized, "invalid number of signer; expected: %d, got %d", len(signers), len(sigs))
	}

	// Try to access the extended account keeper interface
	extendedAK, ok := zscad.ak.(AccountKeeperI)
	if !ok {
		// If we can't access the extended interface, just continue
		return next(ctx, tx, simulate)
	}

	accountsCreated := 0
	for i, signerBytes := range signers {
		if i >= len(sigs) {
			continue // Skip if no corresponding signature
		}

		sig := sigs[i]

		// Validate unordered transaction sequence rules
		if sig.Sequence > 0 && isUnordered {
			return ctx, errorsmod.Wrapf(sdkerrors.ErrInvalidRequest, "sequence is not allowed for unordered transactions")
		}

		// Only create account if sequence is 0 (indicating new account) and not unordered
		if sig.Sequence == 0 && !isUnordered {
			// Convert bytes to AccAddress
			signer := sdk.AccAddress(signerBytes)

			exists := extendedAK.HasAccount(ctx, signer)
			if !exists {
				addrStr, err := extendedAK.AddressCodec().BytesToString(signer)
				if err != nil {
					return ctx, errorsmod.Wrapf(sdkerrors.ErrLogic, "failed to convert signer address: %v", err)
				}

				ctx.Logger().Info("creating new account for zero-sequence transaction",
					"signer_address", addrStr,
					"signer_index", i)

				// Create new account for this signer
				newAccount := extendedAK.NewAccountWithAddress(ctx, signer)
				if newAccount == nil {
					return ctx, errorsmod.Wrapf(sdkerrors.ErrLogic, "failed to create account for signer %s", addrStr)
				}

				extendedAK.SetAccount(ctx, newAccount)

				// Mark as newly created if using AutoCreateAccountKeeper
				if acak, ok := zscad.ak.(*AutoCreateAccountKeeper); ok {
					acak.newlyCreatedAccounts[addrStr] = true
				}

				accountsCreated++

				ctx.Logger().Info("successfully created account for zero-sequence transaction",
					"signer_address", addrStr,
					"account_number", newAccount.GetAccountNumber())
			}
		}
	}

	if accountsCreated > 0 {
		ctx.Logger().Info("ZeroSequenceCreateAccountDecorator completed",
			"accounts_created", accountsCreated)
	}

	return next(ctx, tx, simulate)
}

// ZeroAccountNumberSigVerificationDecorator is an exact clone of NewSigVerificationDecorator
// but hardcodes AccountNumber to 0 for signature verification
type ZeroAccountNumberSigVerificationDecorator struct {
	ak              ante.AccountKeeper
	signModeHandler *txsigning.HandlerMap
	sigVerifyOpts   []ante.SigVerificationDecoratorOption
}

// NewZeroAccountNumberSigVerificationDecorator creates a new ZeroAccountNumberSigVerificationDecorator
func NewZeroAccountNumberSigVerificationDecorator(ak ante.AccountKeeper, signModeHandler *txsigning.HandlerMap, opts ...ante.SigVerificationDecoratorOption) ZeroAccountNumberSigVerificationDecorator {
	return ZeroAccountNumberSigVerificationDecorator{
		ak:              ak,
		signModeHandler: signModeHandler,
		sigVerifyOpts:   opts,
	}
}

// AnteHandle implements the AnteDecorator interface - exactly like SigVerificationDecorator but with AccountNumber: 0
func (svd ZeroAccountNumberSigVerificationDecorator) AnteHandle(ctx sdk.Context, tx sdk.Tx, simulate bool, next sdk.AnteHandler) (sdk.Context, error) {
	sigTx, ok := tx.(authsigning.SigVerifiableTx)
	if !ok {
		return ctx, errorsmod.Wrap(sdkerrors.ErrTxDecode, "invalid transaction type")
	}

	// stdSigs contains the sequence number, account number, and signatures.
	// When simulating, this would just be a 0-length slice.
	sigs, err := sigTx.GetSignaturesV2()
	if err != nil {
		return ctx, err
	}

	signers, err := sigTx.GetSigners()
	if err != nil {
		return ctx, err
	}

	// Get transaction data for signature verification
	adaptableTx, ok := tx.(authsigning.V2AdaptableTx)
	if !ok {
		return ctx, errorsmod.Wrap(sdkerrors.ErrTxDecode, "expected tx to implement V2AdaptableTx")
	}
	txData := adaptableTx.GetSigningTxData()
	chainID := ctx.ChainID()

	for i, sig := range sigs {
		acc, err := ante.GetSignerAcc(ctx, svd.ak, signers[i])
		if err != nil {
			return ctx, err
		}

		pubKey := acc.GetPubKey()
		if pubKey == nil {
			return ctx, errorsmod.Wrapf(sdkerrors.ErrInvalidPubKey, "pubkey on account is not set")
		}

		// Use AccountNumber: 0 hardcoded (this is the key difference from regular SigVerificationDecorator)
		anyPk, err := codectypes.NewAnyWithValue(pubKey)
		if err != nil {
			return ctx, err
		}

		signerData := txsigning.SignerData{
			Address:       acc.GetAddress().String(),
			ChainID:       chainID,
			AccountNumber: 0, // HARDCODED: Always use account number 0
			Sequence:      sig.Sequence,
			PubKey: &anypb.Any{
				TypeUrl: anyPk.TypeUrl,
				Value:   anyPk.Value,
			},
		}

		// Verify the signature using the custom SignerData
		err = authsigning.VerifySignature(ctx, pubKey, signerData, sig.Data, svd.signModeHandler, txData)
		if err != nil {
			return ctx, errorsmod.Wrapf(err, "signature verification failed for signer %s with account number 0", acc.GetAddress())
		}
	}

	return next(ctx, tx, simulate)
}

// ConditionalSigVerificationDecorator wraps SigVerificationDecorator and retries
// with account number 0 for newly created accounts when signature verification fails
type ConditionalSigVerificationDecorator struct {
	ak              ante.AccountKeeper
	signModeHandler *txsigning.HandlerMap
	sigVerifyOpts   []ante.SigVerificationDecoratorOption
}

// NewConditionalSigVerificationDecorator creates a new ConditionalSigVerificationDecorator
func NewConditionalSigVerificationDecorator(ak ante.AccountKeeper, signModeHandler *txsigning.HandlerMap, opts ...ante.SigVerificationDecoratorOption) ConditionalSigVerificationDecorator {
	return ConditionalSigVerificationDecorator{
		ak:              ak,
		signModeHandler: signModeHandler,
		sigVerifyOpts:   opts,
	}
}

// AnteHandle implements the AnteDecorator interface
func (csvd ConditionalSigVerificationDecorator) AnteHandle(ctx sdk.Context, tx sdk.Tx, simulate bool, next sdk.AnteHandler) (sdk.Context, error) {
	// First try the normal signature verification
	sigVerDecorator := ante.NewSigVerificationDecorator(csvd.ak, csvd.signModeHandler, csvd.sigVerifyOpts...)
	newCtx, err := sigVerDecorator.AnteHandle(ctx, tx, simulate, func(ctx sdk.Context, tx sdk.Tx, simulate bool) (sdk.Context, error) {
		return ctx, nil // Don't call next yet
	})

	// If verification succeeded, continue normally
	if err == nil {
		return next(newCtx, tx, simulate)
	}

	// Check if this is a signature verification failure
	if !strings.Contains(err.Error(), "signature verification failed") {
		return ctx, err // Return original error if not signature verification
	}

	ctx.Logger().Info("signature verification failed, checking if retry with account number 0 is needed")

	// Check if we have newly created accounts (sequence 0)
	sigTx, ok := tx.(authsigning.SigVerifiableTx)
	if !ok {
		return ctx, err // Return original error
	}

	sigs, sigErr := sigTx.GetSignaturesV2()
	if sigErr != nil {
		return ctx, err // Return original error
	}

	signers, sigErr := sigTx.GetSigners()
	if sigErr != nil {
		return ctx, err // Return original error
	}

	// Check if any signer has sequence 0 OR is newly created
	hasNewAccount := false
	for i, sig := range sigs {
		if sig.Sequence == 0 && i < len(signers) {
			hasNewAccount = true
			break
		}
		// Also check if account was newly created in this transaction
		if acak, ok := csvd.ak.(*AutoCreateAccountKeeper); ok {
			if i < len(signers) && acak.IsNewlyCreated(sdk.AccAddress(signers[i])) {
				hasNewAccount = true
				break
			}
		}
	}

	if !hasNewAccount {
		return ctx, err // Return original error if no new accounts
	}

	ctx.Logger().Info("retrying signature verification with account number 0 for new accounts")

	// Try using the ZeroAccountNumberSigVerificationDecorator (exact clone with AccountNumber: 0)
	zeroAccountNumberDecorator := NewZeroAccountNumberSigVerificationDecorator(csvd.ak, csvd.signModeHandler, csvd.sigVerifyOpts...)
	newCtx2, err2 := zeroAccountNumberDecorator.AnteHandle(ctx, tx, simulate, func(ctx sdk.Context, tx sdk.Tx, simulate bool) (sdk.Context, error) {
		return ctx, nil // Don't call next yet
	})

	if err2 == nil {
		ctx.Logger().Info("signature verification successful with account number 0")
		return next(newCtx2, tx, simulate)
	}

	// Both attempts failed, return detailed error
	ctx.Logger().Error("signature verification failed with both the newly created account number and account number 0",
		"original_error", err.Error(),
		"retry_error", err2.Error())

	return ctx, errorsmod.Wrapf(err, "signature verification failed with real account number, also failed with account number 0: %v", err2)
}

// NewAnteHandler returns an AnteHandler that checks and increments sequence
// numbers, checks signatures & account numbers, and deducts fees from the first
// signer. It supports automatic account creation for new accounts using sequence 0.
func NewAnteHandler(options HandlerOptions) (sdk.AnteHandler, error) {

	if options.AccountKeeper == nil {
		return nil, errors.New("account keeper is required for ante builder")
	}

	if options.BankKeeper == nil {
		return nil, errors.New("bank keeper is required for ante builder")
	}

	if options.SignModeHandler == nil {
		return nil, errors.New("sign mode handler is required for ante builder")
	}

	anteDecorators := []sdk.AnteDecorator{
		ante.NewSetUpContextDecorator(), // outermost AnteDecorator. SetUpContext must be called first
		ante.NewExtensionOptionsDecorator(options.ExtensionOptionChecker),
		ante.NewValidateBasicDecorator(),
		ante.NewTxTimeoutHeightDecorator(),
		NewZeroSequenceCreateAccountDecorator(options.AccountKeeper), // MOVED: Create accounts BEFORE SetPubKeyDecorator
		ante.NewSetPubKeyDecorator(options.AccountKeeper),
		ante.NewValidateMemoDecorator(options.AccountKeeper),
		ante.NewConsumeGasForTxSizeDecorator(options.AccountKeeper),
		NewConditionalDeductFeeDecorator(options.AccountKeeper, options.BankKeeper, options.FeegrantKeeper, options.TxFeeChecker),
		ante.NewValidateSigCountDecorator(options.AccountKeeper),
		ante.NewSigGasConsumeDecorator(options.AccountKeeper, options.SigGasConsumer),
		NewConditionalSigVerificationDecorator(options.AccountKeeper, options.SignModeHandler, options.SigVerifyOptions...), // Use conditional wrapper
		ante.NewIncrementSequenceDecorator(options.AccountKeeper),
	}

	return sdk.ChainAnteDecorators(anteDecorators...), nil
}
