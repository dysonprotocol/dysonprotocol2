export interface Provider {
  address: string;
  bond: string;
  reputation: {
    correct: number;
    slashed: number;
    total: number;
  };
  status: "active" | "inactive";
  registered_at: number;
}

export interface CommitEntry {
  hash: string;
  timestamp: string;
}

export interface RevealEntry {
  response: unknown;
  timestamp: string;
}

export interface Request {
  request_id: number;
  requester: string;
  prompt: string;
  response_schema: Record<string, unknown>;
  scorer: string;
  fee: string;
  callback_script: string | null;
  callback_fn: string | null;
  created_at: number;
  status: "pending" | "active" | "revealing" | "resolved" | "failed";
  commits: Record<string, CommitEntry>;
  reveals: Record<string, RevealEntry>;
  result: unknown;
  scores: Record<string, number>;
  commit_deadline?: string;  // ISO timestamp
  reveal_deadline?: string;  // ISO timestamp
  finalize_phase?: "scoring" | "settling" | "complete";
  scorer_state?: unknown;
  processed_providers?: string[];
}

export interface ProtocolState {
  next_request_id: number;
  min_bond: string;
  active_request_id: number | null;
  commit_timeout_seconds: number;
  reveal_timeout_seconds: number;
}
