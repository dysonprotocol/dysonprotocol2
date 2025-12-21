export const SCRIPT_ADDRESS = "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej";
export const ENERGY_DENOM = "rps.dys/energy";
export const JOIN_COST = 100;

export const TokenType = {
  ROCK: 0,
  PAPER: 1,
  SCISSORS: 2,
} as const;

export type TokenTypeName = "rock" | "paper" | "scissors";

export const Direction = {
  N: 0,
  S: 1,
  E: 2,
  W: 3,
} as const;

export type DirectionName = keyof typeof Direction;

export interface Token {
  id: number | string;
  owner: string;
  type: string; // 'rock' | 'paper' | 'scissors' | 'snail' | 'energy'
  x: number;
  y: number;
  nonce: number;
  state: string; // 'active' | 'pending_battle' | 'dead'
  amount?: number; // For energy pieces only
}

export interface Snail {
  id: string;
  x: number;
  y: number;
}

export interface PendingBattle {
  attacker_id: string;
  defender_id: string;
  x: number;
  y: number;
}

// What get_game_status actually returns
export interface GameConfig {
  join_cost: number;
  attack_reward: number;
}

export interface GameStateData {
  total_pieces: number;
  last_updated_block: number;
  next_piece_id: number;
}

export interface GameState {
  config: GameConfig | null;
  state: GameStateData | null;
  // Legacy fields for grid display (not populated by get_game_status)
  tokens?: Record<string, Token>;
  tick?: number;
  snails?: Record<string, Snail>;
  pending_battles?: PendingBattle[];
}

export const TYPE_NAMES: Record<number, TokenTypeName> = {
  0: "rock",
  1: "paper",
  2: "scissors",
};

export const TYPE_EMOJIS: Record<string, string> = {
  rock: "🪨",
  paper: "📄",
  scissors: "✂️",
  snail: "🐌",
  energy: "⚡",
};

export const DIRECTION_ARROWS: Record<DirectionName, string> = {
  N: "↑",
  S: "↓",
  E: "→",
  W: "←",
};

export const DIRECTION_OFFSETS: Record<
  DirectionName,
  { dx: number; dy: number }
> = {
  N: { dx: 0, dy: -1 },
  S: { dx: 0, dy: 1 },
  E: { dx: 1, dy: 0 },
  W: { dx: -1, dy: 0 },
};

// Player stats for leaderboard
export interface PlayerStats {
  address: string;
  pieces: number[];
  total_kills: number;
  total_deaths: number;
  total_spawns: number;
  energy_earned: number;
  energy_spent: number;
  total_blocks_alive: number;
  max_piece_lifespan: number;
  total_collections: number;
  total_moves: number;
  peak_pieces: number;
}
