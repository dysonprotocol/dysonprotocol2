package whaleswap

const (
	ModuleName  = "whaleswap"
	StoreKey    = ModuleName
	RouterKey   = ModuleName
	MemStoreKey = "mem_whaleswap"
	// LeverageVaultModuleName is a dedicated module account used to escrow leverage-held assets
	// and act as the trader counterparty for internal AMM settlement during leverage operations.
	LeverageVaultModuleName = "whaleswap_leverage_vault"
	// LeverageBorrowVaultModuleName is a dedicated module account that receives loaned (borrowed)
	// tokens before trading; it isolates loan prefunding from trading escrow for clarity.
	LeverageBorrowVaultModuleName = "whaleswap_leverage_borrow_vault"
	// ArbRevenueModuleName is a dedicated module account that receives arbitrage profits.
	// Protocol-captured MEV from circular arbitrage trades is deposited here.
	ArbRevenueModuleName = "whaleswap_arb_revenue"
)
