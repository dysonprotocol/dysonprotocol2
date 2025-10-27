## Whaleswap Leverage: Accounting, Invariants and Vault Design

### 1) Initial problem
- Invariants failed after adding leverage because token flows were not fully accounted:
  - OpenPosition increased `pool.TotalBorrowed` and computed a synthetic "held" without performing a real AMM swap or bank settlement.
  - ClosePosition returned collateral/profit from the module without an escrowed source, reducing the module’s bank balance below AMM reserves.
- Resulting errors: "module balance below AMM reserves" and unified module balance mismatches.

### 2) Current solution (implemented)
- Introduced leverage vault (`whaleswap_leverage_vault`) and borrow vault (`whaleswap_leverage_borrow_vault`) module accounts plus keeper helpers.
- Invariants:
  - Unified module-balance check counts only the whaleswap module account; vaults are treated as external traders.
  - Expected balances include leverage collateral held in-module.
- Leverage flows use PoolSwap with the vault as trader; settlement via `wsMoveCoins` keeps module bank balances aligned with pool reserves. Invariants are asserted at the end of leverage messages.

### 3) Things to consider
- Settlement source of truth: AMM reserves live in the whaleswap module; bank movements must track pool reserve deltas exactly per denom.
- tradeApplySwapLeg updates pool state but does not perform bank settlement; using PoolSwap/MakeTrade paths guarantees `wsMoveCoins` settlement.
- AMM invariants currently check whaleswap module balances only; either:
  - Keep reserves strictly in whaleswap module (preferred) and use the vault as the trader so `wsMoveCoins` nets module coins to pool reserves; or
  - Extend AMM invariant coverage to include the vault if reserves can transiently sit there (less clean).
- Collateral vs. held separation: collateral belongs in whaleswap module; held belongs in the vault to keep responsibilities crisp.
- Interest/repayment: repayment must be realized in borrowed denom and accounted in `pool.TotalBorrowed` and `pool.InterestEarned` without violating invariants.

### 4) Next steps
- Add a dedicated borrow vault module account (e.g., `whaleswap_leverage_borrow_vault`) to separate loan prefunding from trading escrow (optional but clarifying).
- Route leverage Open/Close through PoolSwap (or MakeTrade with a single SwapLeg) using the vault as `trader`:
  - Open: vault performs exact-in swap (borrow → held); `wsMoveCoins` settles per-denom deltas; position holds "held" in the vault; collateral escrowed in whaleswap module.
  - Close: vault performs exact-in swap (held → borrowed), compute repayment+interest, repay pool (module-to-module if needed), return remaining collateral and pay profit to user.
- Ensure AMM invariants continue to pass without summing extra accounts by keeping final reserves strictly in whaleswap module after each operation.
- Remove reliance on direct pool math in leverage handlers; exclusively reuse PoolSwap path to guarantee settlement correctness and reduce code surface.
- Expand tests:
  - Happy paths (CLI) verifying Open→Close cycles preserve all invariants and event correctness.
  - Error paths (sudo/query) for fast checks (CR, leverage limits, ownership, block delays).
- Document vault responsibilities and flows in module docs to avoid regressions.

### Status (progress)
- Implemented:
  - Borrow vault account and helpers.
  - OpenPosition: loan moved module→borrow vault; PoolSwap (borrow→held) executed with borrow vault as trader; position persisted; invariants asserted.
  - ClosePosition: PoolSwap (held→borrow) executed with borrow vault as trader; repayment coin moved borrow vault→whaleswap module and added to pool reserves; `TotalBorrowed` decreased; `InterestEarned` increased; remaining collateral returned from module; profit paid from borrow vault; invariants asserted.
- Invariants now: actual = whaleswap module only; expected includes leverage collateral; vaults excluded (treated as traders). AMM coverage relies on PoolSwap settlement+module-to-module repayment transfer.
- Pending: Tests (CLI happy paths for Open/Close; query-mode error paths), docs polish, and small UX enhancements.

### Keep in mind
- Vaults are traders: do not include vault balances in the unified module-balance check; ensure final pool reserves always reside in the whaleswap module by end-of-msg.
- Repayment shortfall currently requires `collateral.denom == borrowed.denom`. Consider an automatic internal swap path for covering shortfalls with non-matching collateral.
- Profit is paid from the borrow vault after repayment; by construction, `profit = proceeds - repayment`. Ensure PoolSwap + repayment transfer leaves no stranded dust.
- Always assert AMM + unified invariants at the end of leverage msgs to guard regressions.
- Tests should validate both events and per-denom bank balances match pool reserve changes.


