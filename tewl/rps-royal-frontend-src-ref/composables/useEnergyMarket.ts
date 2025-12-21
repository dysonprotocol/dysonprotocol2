import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import axios from "axios";
import { ENERGY_DENOM } from "@/types/game";
import { useWallet } from "./useWallet";

// Whaleswap pool ID for energy/DYS pair
export const ENERGY_POOL_ID = "6";
const DYS_DENOM = "udys";

interface Coin {
  denom: string;
  amount: string;
}

interface DecCoin {
  denom: string;
  amount: string;
}

interface Pool {
  pool_id: string;
  coins: Coin[];
  fee_rate?: DecCoin[];
  fee_pct?: string; // deprecated fallback
}

interface PoolResponse {
  pool: Pool;
}

interface SwapOperation {
  swap?: { pool_id: string };
  sent?: Coin;
  received?: Coin;
}

interface Trade {
  trade_id: string;
  trader: string;
  height: string;
  timestamp: string;
  operations: SwapOperation[];
  total_sent: Coin[];
  total_received: Coin[];
}

interface TradesResponse {
  trades: Trade[];
  pagination?: { next_key: string; total: string };
}

interface PricePoint {
  idx: number;
  price: number;
  tradeId: string;
  timestamp: string;
}

/**
 * Fetch last N trades for the energy/DYS pool from whaleswap API
 */
async function fetchEnergyTrades(limit = 100): Promise<Trade[]> {
  const url = `/dysonprotocol/whaleswap/v1/trades/pool/${ENERGY_POOL_ID}`;
  const params = new URLSearchParams({
    "pagination.limit": String(limit),
    "pagination.reverse": "true", // Most recent first
  });

  try {
    const resp = await axios.get<TradesResponse>(`${url}?${params}`);
    return resp.data.trades || [];
  } catch (error) {
    console.error("[useEnergyMarket] fetchEnergyTrades error:", error);
    return [];
  }
}

/**
 * Convert trades to price points
 * Price = DYS per energy unit
 */
function tradesToPriceHistory(trades: Trade[]): PricePoint[] {
  const points: PricePoint[] = [];

  for (const trade of trades) {
    if (!trade.operations) continue;

    for (const op of trade.operations) {
      if (!op.swap || String(op.swap.pool_id) !== ENERGY_POOL_ID) continue;
      if (!op.sent || !op.received) continue;

      const sentDenom = op.sent.denom;
      const receivedDenom = op.received.denom;
      const sentAmount = BigInt(op.sent.amount);
      const receivedAmount = BigInt(op.received.amount);

      if (sentAmount === 0n || receivedAmount === 0n) continue;

      let price: number | null = null;

      // Calculate price as DYS per energy
      if (sentDenom === ENERGY_DENOM && receivedDenom === "udys") {
        // Sold energy, got DYS: price = received_dys / sent_energy
        price = Number(receivedAmount) / Number(sentAmount);
      } else if (sentDenom === "udys" && receivedDenom === ENERGY_DENOM) {
        // Bought energy with DYS: price = sent_dys / received_energy
        price = Number(sentAmount) / Number(receivedAmount);
      }

      if (price !== null && isFinite(price) && price > 0) {
        points.push({
          idx: points.length,
          price,
          tradeId: trade.trade_id,
          timestamp: trade.timestamp,
        });
      }
    }
  }

  // Reverse so oldest is first (chronological order for chart)
  points.reverse();

  // Re-index after reverse
  points.forEach((p, i) => (p.idx = i));

  return points;
}

/**
 * Fetch pool data for swap calculations
 */
async function fetchEnergyPool(): Promise<Pool | null> {
  const url = `/dysonprotocol/whaleswap/v1/pool/${ENERGY_POOL_ID}`;
  const resp = await axios.get<PoolResponse>(url);
  return resp.data.pool || null;
}

/**
 * Get fee rate for a given output denom
 */
function getFeeRate(pool: Pool, outputDenom: string): number {
  if (pool.fee_rate && Array.isArray(pool.fee_rate)) {
    const feeCoin = pool.fee_rate.find((f) => f.denom === outputDenom);
    if (feeCoin) return parseFloat(feeCoin.amount);
  }
  if (pool.fee_pct) return parseFloat(pool.fee_pct);
  return 0;
}

/**
 * Calculate swap output for exact input (AMM constant product formula)
 */
function calculateSwapOutput(
  pool: Pool,
  inputAmount: string,
  inputDenom: string
): string {
  if (!inputAmount || !pool.coins || pool.coins.length !== 2) return "";

  const inputCoin = pool.coins.find((c) => c.denom === inputDenom);
  const outputCoin = pool.coins.find((c) => c.denom !== inputDenom);
  if (!inputCoin || !outputCoin) return "";

  const inputReserve = BigInt(inputCoin.amount);
  const outputReserve = BigInt(outputCoin.amount);
  if (inputReserve === 0n || outputReserve === 0n) return "";

  const inputAmt = BigInt(inputAmount);
  if (inputAmt === 0n) return "";

  const feeRate = getFeeRate(pool, outputCoin.denom);
  const feeMultiplier = 1 - feeRate;
  const feeMultiplierInt = BigInt(Math.floor(feeMultiplier * 1000000));

  const numerator = inputAmt * outputReserve * feeMultiplierInt;
  const denominator =
    inputReserve * BigInt(1000000) + inputAmt * feeMultiplierInt;
  if (denominator === 0n) return "";

  return String(numerator / denominator);
}

/**
 * Calculate swap input for exact output (AMM constant product formula)
 */
function calculateSwapInput(
  pool: Pool,
  outputAmount: string,
  outputDenom: string
): string {
  if (!outputAmount || !pool.coins || pool.coins.length !== 2) return "";

  const outputCoin = pool.coins.find((c) => c.denom === outputDenom);
  const inputCoin = pool.coins.find((c) => c.denom !== outputDenom);
  if (!inputCoin || !outputCoin) return "";

  const inputReserve = BigInt(inputCoin.amount);
  const outputReserve = BigInt(outputCoin.amount);
  if (inputReserve === 0n || outputReserve === 0n) return "";

  const outputAmt = BigInt(outputAmount);
  if (outputAmt === 0n) return "";

  const feeRate = getFeeRate(pool, outputDenom);
  const feeMultiplier = 1 - feeRate;
  const feeMultiplierInt = BigInt(Math.floor(feeMultiplier * 1000000));

  // rawOutputAmt = outputAmt / feeMultiplier
  const rawOutputAmt = (outputAmt * BigInt(1000000)) / feeMultiplierInt;
  if (rawOutputAmt >= outputReserve) return "";

  const numerator = rawOutputAmt * inputReserve;
  const denominator = outputReserve - rawOutputAmt;
  if (denominator === 0n) return "";

  // Round up for input calculation
  return String((numerator + denominator - 1n) / denominator);
}

/**
 * Calculate spot price from pool reserves (DYS per energy)
 */
function getPoolSpotPrice(pool: Pool | null): number | null {
  if (!pool?.coins || pool.coins.length !== 2) return null;
  const energyCoin = pool.coins.find((c) => c.denom === ENERGY_DENOM);
  const dysCoin = pool.coins.find((c) => c.denom === DYS_DENOM);
  if (!energyCoin || !dysCoin) return null;
  const energyReserve = Number(energyCoin.amount);
  const dysReserve = Number(dysCoin.amount);
  if (energyReserve === 0) return null;
  return dysReserve / energyReserve;
}

/**
 * Composable for energy market price data
 */
export function useEnergyMarket(limit = 100) {
  const tradesQuery = useQuery({
    queryKey: ["energyTrades", limit],
    queryFn: () => fetchEnergyTrades(limit),
    refetchInterval: 10000, // Refresh every 10s
    staleTime: 5000,
  });

  // Pool query for current spot price
  const poolQuery = useQuery({
    queryKey: ["energyPool"],
    queryFn: fetchEnergyPool,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  // Current price from pool reserves (true spot price)
  const currentPrice = computed(() => getPoolSpotPrice(poolQuery.data.value));

  // Price history from trades + current pool price appended
  const priceHistory = computed(() => {
    const tradePoints = tradesQuery.data.value
      ? tradesToPriceHistory(tradesQuery.data.value)
      : [];
    const spotPrice = currentPrice.value;
    if (spotPrice === null) return tradePoints;
    // Append current pool price as final point
    return [
      ...tradePoints,
      {
        idx: tradePoints.length,
        price: spotPrice,
        tradeId: "current",
        timestamp: new Date().toISOString(),
      },
    ];
  });

  const priceStart = computed(() => {
    const history = priceHistory.value;
    if (history.length === 0) return null;
    return history[0].price;
  });

  const priceChange = computed(() => {
    const start = priceStart.value;
    const current = currentPrice.value;
    if (start === null || current === null || start === 0) return 0;
    return ((current - start) / start) * 100;
  });

  const isUp = computed(() => priceChange.value >= 0);

  return {
    priceHistory,
    currentPrice,
    priceStart,
    priceChange,
    isUp,
    isLoading: tradesQuery.isLoading || poolQuery.isLoading,
    error: tradesQuery.error,
    refetch: tradesQuery.refetch,
  };
}

/**
 * Composable for energy swap operations
 * - Buy: exact swap_out for ENERGY_DENOM (user specifies energy amount to receive)
 * - Sell: exact swap_in for ENERGY_DENOM (user specifies energy amount to sell)
 */
export function useEnergySwap() {
  const { wallet, sendMsg } = useWallet();
  const queryClient = useQueryClient();
  const isPending = ref(false);
  const error = ref<string | null>(null);

  // Pool query for swap calculations
  const poolQuery = useQuery({
    queryKey: ["energyPool"],
    queryFn: fetchEnergyPool,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const pool = computed(() => poolQuery.data.value);

  /**
   * Get quote for buying energy (how much DYS needed for given energy amount)
   */
  function getBuyQuote(energyAmount: number): string | null {
    if (!pool.value || energyAmount <= 0) return null;
    const input = calculateSwapInput(
      pool.value,
      String(energyAmount),
      ENERGY_DENOM
    );
    return input || null;
  }

  /**
   * Get quote for selling energy (how much DYS received for given energy amount)
   */
  function getSellQuote(energyAmount: number): string | null {
    if (!pool.value || energyAmount <= 0) return null;
    const output = calculateSwapOutput(
      pool.value,
      String(energyAmount),
      ENERGY_DENOM
    );
    return output || null;
  }

  /**
   * Buy energy - exact swap_out for ENERGY_DENOM
   * User specifies how much energy they want to receive
   */
  async function buyEnergy(energyAmount: number, slippagePct = 0.5) {
    if (!wallet.value.address) throw new Error("Wallet not connected");
    if (!pool.value) throw new Error("Pool data not loaded");
    if (energyAmount <= 0) throw new Error("Amount must be positive");

    const exactEnergyOut = String(energyAmount);
    const expectedDysIn = calculateSwapInput(
      pool.value,
      exactEnergyOut,
      ENERGY_DENOM
    );
    if (!expectedDysIn) throw new Error("Could not calculate swap input");

    // Add slippage buffer to max input
    const maxDysIn = String(
      BigInt(Math.ceil(Number(expectedDysIn) * (1 + slippagePct / 100)))
    );

    const msg = {
      "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
      trader: wallet.value.address,
      max_input: [{ denom: DYS_DENOM, amount: maxDysIn }],
      operations: [
        {
          swap: {
            pool_id: ENERGY_POOL_ID,
            swap_out: { denom: ENERGY_DENOM, amount: exactEnergyOut },
          },
        },
      ],
      min_output: [{ denom: ENERGY_DENOM, amount: exactEnergyOut }],
      note: "",
    };

    isPending.value = true;
    error.value = null;

    const result = await sendMsg({
      msg,
      executorAddress: wallet.value.address,
      gasLimit: "auto",
    });

    isPending.value = false;

    if (!result.success) {
      const errMsg = result.rawLog || "Buy failed";
      error.value = errMsg;
      throw new Error(errMsg);
    }

    // Invalidate queries to refresh balances
    queryClient.invalidateQueries({ queryKey: ["energyBalance"] });
    queryClient.invalidateQueries({ queryKey: ["energyPool"] });
    queryClient.invalidateQueries({ queryKey: ["energyTrades"] });

    return result;
  }

  /**
   * Sell energy - exact swap_in for ENERGY_DENOM
   * User specifies how much energy they want to sell
   */
  async function sellEnergy(energyAmount: number, slippagePct = 0.5) {
    if (!wallet.value.address) throw new Error("Wallet not connected");
    if (!pool.value) throw new Error("Pool data not loaded");
    if (energyAmount <= 0) throw new Error("Amount must be positive");

    const exactEnergyIn = String(energyAmount);
    const expectedDysOut = calculateSwapOutput(
      pool.value,
      exactEnergyIn,
      ENERGY_DENOM
    );
    if (!expectedDysOut) throw new Error("Could not calculate swap output");

    // Apply slippage to min output
    const minDysOut = String(
      BigInt(Math.floor(Number(expectedDysOut) * (1 - slippagePct / 100)))
    );

    const msg = {
      "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
      trader: wallet.value.address,
      max_input: [{ denom: ENERGY_DENOM, amount: exactEnergyIn }],
      operations: [
        {
          swap: {
            pool_id: ENERGY_POOL_ID,
            swap_in: { denom: ENERGY_DENOM, amount: exactEnergyIn },
          },
        },
      ],
      min_output: [{ denom: DYS_DENOM, amount: minDysOut }],
      note: "",
    };

    isPending.value = true;
    error.value = null;

    const result = await sendMsg({
      msg,
      executorAddress: wallet.value.address,
      gasLimit: "auto",
    });

    isPending.value = false;

    if (!result.success) {
      const errMsg = result.rawLog || "Sell failed";
      error.value = errMsg;
      throw new Error(errMsg);
    }

    // Invalidate queries to refresh balances
    queryClient.invalidateQueries({ queryKey: ["energyBalance"] });
    queryClient.invalidateQueries({ queryKey: ["energyPool"] });
    queryClient.invalidateQueries({ queryKey: ["energyTrades"] });

    return result;
  }

  return {
    pool,
    isPending,
    error,
    isPoolLoading: poolQuery.isLoading,
    getBuyQuote,
    getSellQuote,
    buyEnergy,
    sellEnergy,
    refetchPool: poolQuery.refetch,
  };
}
