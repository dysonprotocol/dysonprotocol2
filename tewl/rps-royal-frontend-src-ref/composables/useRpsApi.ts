import {
  SCRIPT_ADDRESS,
  ENERGY_DENOM,
  type GameState,
  type Token,
  type GameConfig,
  type GameStateData,
  type PlayerStats,
} from "@/types/game";
import axios from "axios";

// ============================================================================
// Storage API - Direct queries to on-chain storage (no script execution)
// ============================================================================

interface StorageEntry {
  owner: string;
  index: string;
  data: string;
  updated_height: string;
  updated_timestamp: string;
  hash: string;
}

interface StorageGetResponse {
  entry: StorageEntry;
}

interface StorageListResponse {
  entries: StorageEntry[];
  pagination?: {
    next_key: string;
    total: string;
  };
}

// Get a single storage entry
async function storageGet<T>(index: string): Promise<T | null> {
  const url = `/dysonprotocol/storage/v1/storage_get?owner=${SCRIPT_ADDRESS}&index=${encodeURIComponent(
    index
  )}`;
  try {
    const resp = await axios.get<StorageGetResponse>(url);
    return JSON.parse(resp.data.entry.data) as T;
  } catch (error: any) {
    if (error.response?.status === 404 || error.response?.data?.code === 5) {
      return null;
    }
    throw error;
  }
}

// List storage entries by prefix
async function storageList<T>(
  indexPrefix: string
): Promise<Array<{ index: string; data: T }>> {
  const url = `/dysonprotocol/storage/v1/storage_list?owner=${SCRIPT_ADDRESS}&index_prefix=${encodeURIComponent(
    indexPrefix
  )}`;
  try {
    const resp = await axios.get<StorageListResponse>(url);
    const entries = resp.data.entries || [];
    return entries.map((entry) => ({
      index: entry.index,
      data: JSON.parse(entry.data) as T,
    }));
  } catch (error: any) {
    if (error.response?.status === 404) return [];
    throw error;
  }
}

// ============================================================================
// Game Data Fetchers
// ============================================================================

export async function fetchGameState(): Promise<GameState> {
  console.log("[API] fetchGameState() via storage");

  // Fetch config and state directly from storage
  const [config, state] = await Promise.all([
    storageGet<GameConfig>("game/config"),
    storageGet<GameStateData>("game/state"),
  ]);

  // Fetch all pieces
  const pieceEntries = await storageList<any>("game/pieces/");

  const tokens: Record<string, Token> = {};
  for (const { data: piece } of pieceEntries) {
    if (piece) {
      tokens[String(piece.id)] = {
        id: piece.id,
        owner: piece.owner || "", // Energy pieces have no owner
        type: piece.type,
        x: piece.x,
        y: piece.y,
        nonce: 0,
        state: "active",
        amount: piece.amount, // For energy pieces
      };
    }
  }

  console.log("[API] fetchGameState() tokens:", Object.keys(tokens).length);

  return {
    config,
    state,
    tokens,
  };
}

export async function fetchAllPieces(): Promise<Token[]> {
  console.log("[API] fetchAllPieces() via storage");

  const pieceEntries = await storageList<any>("game/pieces/");

  const pieces: Token[] = [];
  for (const { data: piece } of pieceEntries) {
    if (piece && piece.type !== "snail") {
      pieces.push({
        id: piece.id,
        owner: piece.owner || "",
        type: piece.type,
        x: piece.x,
        y: piece.y,
        nonce: 0,
        state: "active",
        amount: piece.amount,
      });
    }
  }

  console.log("[API] fetchAllPieces() found", pieces.length, "pieces");
  return pieces;
}

export async function fetchOwnedTokens(owner: string): Promise<Token[]> {
  console.log("[API] fetchOwnedTokens() for", owner);

  // Get player data which has list of piece IDs
  const playerData = await storageGet<{ pieces: number[] }>(
    `game/players/${owner}`
  );

  if (!playerData?.pieces?.length) {
    console.log("[API] fetchOwnedTokens() no pieces for player");
    return [];
  }

  // Fetch each piece
  const pieces: Token[] = [];
  for (const pieceId of playerData.pieces) {
    const paddedId = String(pieceId).padStart(10, "0");
    const piece = await storageGet<any>(`game/pieces/${paddedId}`);
    if (piece && piece.type !== "energy") {
      pieces.push({
        id: piece.id,
        owner: piece.owner,
        type: piece.type,
        x: piece.x,
        y: piece.y,
        nonce: 0,
        state: "active",
      });
    }
  }

  console.log("[API] fetchOwnedTokens() found", pieces.length, "pieces");
  return pieces;
}

export async function fetchBalance(
  address: string,
  denom = "udys"
): Promise<string> {
  console.log("[API] fetchBalance() for", address, denom);
  try {
    const resp = await axios.get(
      `/cosmos/bank/v1beta1/balances/${address}/by_denom?denom=${encodeURIComponent(
        denom
      )}`
    );
    return resp.data.balance?.amount || "0";
  } catch (error) {
    console.error("[API] fetchBalance() error:", error);
    return "0";
  }
}

export async function fetchEnergyBalance(address: string): Promise<string> {
  return fetchBalance(address, ENERGY_DENOM);
}

export async function fetchLeaderboard(): Promise<PlayerStats[]> {
  console.log("[API] fetchLeaderboard() via storage");

  const playerEntries = await storageList<Omit<PlayerStats, "address">>(
    "game/players/"
  );

  const players: PlayerStats[] = [];
  for (const { index, data } of playerEntries) {
    // Extract address from index: "game/players/dys1..."
    const address = index.replace("game/players/", "");
    // Skip NPCs (snail has owner=None)
    if (!address || address === "None" || address === "none") continue;
    players.push({
      address,
      pieces: data.pieces || [],
      total_kills: data.total_kills || 0,
      total_deaths: data.total_deaths || 0,
      total_spawns: data.total_spawns || 0,
      energy_earned: data.energy_earned || 0,
      energy_spent: data.energy_spent || 0,
      total_blocks_alive: data.total_blocks_alive || 0,
      max_piece_lifespan: data.max_piece_lifespan || 0,
      total_collections: data.total_collections || 0,
      total_moves: data.total_moves || 0,
      peak_pieces: data.peak_pieces || 0,
    });
  }

  console.log("[API] fetchLeaderboard() found", players.length, "players");
  return players;
}

// ============================================================================
// Energy Token Queries
// ============================================================================

export interface EnergyHolder {
  address: string;
  balance: number;
  percent: number;
}

interface DenomOwner {
  address: string;
  balance: { denom: string; amount: string };
}

interface DenomOwnersResponse {
  denom_owners: DenomOwner[];
  pagination?: { next_key: string; total: string };
}

interface SupplyResponse {
  amount: { denom: string; amount: string };
}

export async function fetchEnergyHolders(): Promise<EnergyHolder[]> {
  console.log("[API] fetchEnergyHolders()");

  // Fetch total supply and holders in parallel
  const [supplyResp, ownersResp] = await Promise.all([
    axios.get<SupplyResponse>(
      `/cosmos/bank/v1beta1/supply/by_denom?denom=${encodeURIComponent(ENERGY_DENOM)}`
    ),
    axios.get<DenomOwnersResponse>(
      `/cosmos/bank/v1beta1/denom_owners/${encodeURIComponent(ENERGY_DENOM)}?pagination.limit=100`
    ),
  ]);

  const totalSupply = parseInt(supplyResp.data.amount?.amount || "0", 10);
  const owners = ownersResp.data.denom_owners || [];

  if (totalSupply === 0) return [];

  const holders: EnergyHolder[] = owners
    .map((o) => {
      const balance = parseInt(o.balance?.amount || "0", 10);
      return {
        address: o.address,
        balance,
        percent: (balance / totalSupply) * 100,
      };
    })
    .filter((h) => h.balance > 0)
    .sort((a, b) => b.balance - a.balance);

  console.log("[API] fetchEnergyHolders() found", holders.length, "holders");
  return holders;
}

// ============================================================================
// Board Bounds Calculation
// ============================================================================

export function calculateBoardBounds(totalPieces: number): {
  min: number;
  max: number;
} {
  // Board size: -numPieces to numPieces per side
  return {
    min: -totalPieces,
    max: totalPieces,
  };
}
