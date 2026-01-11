/**
 * State Channel Helpers (40-11)
 *
 * Utility functions for hash generation, salt creation, and topic building.
 */

import { sha256 } from '@cosmjs/crypto'
import { toHex } from '@cosmjs/encoding'

// =============================================================================
// Commitment Hash
// =============================================================================

/**
 * Create commitment hash: sha256(result + ":" + salt)
 * Must match the on-chain _compute_commitment_hash function.
 *
 * @param result - JSON-stringified computation result
 * @param salt - 64-char hex salt
 * @returns 64-char lowercase hex hash
 */
export function createCommitmentHash(result: string, salt: string): string {
  const input = `${result}:${salt}`
  return toHex(sha256(new TextEncoder().encode(input)))
}

// =============================================================================
// Salt Generation
// =============================================================================

/**
 * Generate cryptographically secure 32-byte random salt.
 * Uses Web Crypto API for browser compatibility.
 *
 * @returns 64-char lowercase hex string
 */
export function generateSalt(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return toHex(bytes)
}

// =============================================================================
// Attestation Hash
// =============================================================================

/**
 * Create deterministic attestation hash for non-participation proof.
 * Must match the on-chain make_attestation_hash function.
 *
 * @param accused - Address of non-participating member
 * @param channel_id - Channel identifier
 * @param step - Step number
 * @param timestamp - Unix timestamp (ms)
 * @returns 64-char lowercase hex hash
 */
export function createAttestationHash(
  accused: string,
  channel_id: string,
  step: number,
  timestamp: number
): string {
  // Matches Python: json.dumps({"accused": ..., "channel_id": ..., "step": ..., "timestamp": ...})
  // JSON.stringify produces same output for simple objects
  const input = JSON.stringify({ accused, channel_id, step, timestamp })
  return toHex(sha256(new TextEncoder().encode(input)))
}

// =============================================================================
// Topic Building
// =============================================================================

/**
 * Build GossipSub topic for a state channel.
 * Topic format: {topicPrefix}sc/{channelId}
 *
 * @param topicPrefix - Chain-specific prefix (e.g., "/localnet/v1/")
 * @param channelId - Channel identifier
 * @returns Full topic string
 */
export function buildChannelTopic(
  topicPrefix: string,
  channelId: string
): string {
  const prefix = topicPrefix.endsWith('/') ? topicPrefix : `${topicPrefix}/`
  return `${prefix}sc/${channelId}`
}

// =============================================================================
// Result Hashing
// =============================================================================

/**
 * Hash a computation result for verification.
 * Must match the on-chain hash_json function.
 *
 * @param result - Computation result object
 * @returns 64-char lowercase hex hash
 */
export function hashResult(result: unknown): string {
  const json = JSON.stringify(result)
  return toHex(sha256(new TextEncoder().encode(json)))
}

/**
 * Hash a string value.
 * Must match the on-chain hash_str function.
 */
export function hashString(data: string): string {
  return toHex(sha256(new TextEncoder().encode(data)))
}

/**
 * Chain hash for merkle chain verification.
 * step_n_hash = sha256(prev_hash + step_n_data_json)
 *
 * @param prevHash - Previous step hash (64-char hex)
 * @param data - Current step data
 * @returns 64-char lowercase hex hash
 */
export function chainHash(prevHash: string, data: unknown): string {
  const dataJson = JSON.stringify(data)
  const input = prevHash + dataJson
  return toHex(sha256(new TextEncoder().encode(input)))
}

