/**
 * State Channel Message Validation (40-11)
 *
 * Type guards and verification functions for state channel messages.
 * Critical for unanimous consensus - all reveals must match.
 */

import { sha256 } from '@cosmjs/crypto'
import { toHex } from '@cosmjs/encoding'
import type {
  StateChannelMessage,
  CommitmentMessage,
  RevealMessage,
  NonParticipationAttestation,
} from './types'

// =============================================================================
// Type Guards
// =============================================================================

/**
 * Check if value is a valid CommitmentMessage.
 * Validates: type, channel_id, step, timestamp, commitment_hash (64-char hex)
 */
export function isCommitmentMessage(msg: unknown): msg is CommitmentMessage {
  if (!msg || typeof msg !== 'object') return false
  const m = msg as Record<string, unknown>
  return (
    m.type === 'COMMITMENT' &&
    typeof m.channel_id === 'string' &&
    m.channel_id.length > 0 &&
    typeof m.step === 'number' &&
    m.step >= 0 &&
    Number.isInteger(m.step) &&
    typeof m.timestamp === 'number' &&
    typeof m.commitment_hash === 'string' &&
    /^[0-9a-f]{64}$/i.test(m.commitment_hash)
  )
}

/**
 * Check if value is a valid RevealMessage.
 * Validates: type, channel_id, step, timestamp, result (non-empty), salt (64-char hex)
 */
export function isRevealMessage(msg: unknown): msg is RevealMessage {
  if (!msg || typeof msg !== 'object') return false
  const m = msg as Record<string, unknown>
  return (
    m.type === 'REVEAL' &&
    typeof m.channel_id === 'string' &&
    m.channel_id.length > 0 &&
    typeof m.step === 'number' &&
    m.step >= 0 &&
    Number.isInteger(m.step) &&
    typeof m.timestamp === 'number' &&
    typeof m.result === 'string' &&
    typeof m.salt === 'string' &&
    /^[0-9a-f]{64}$/i.test(m.salt)
  )
}

/**
 * Check if value is a valid NonParticipationAttestation.
 * Validates: type, channel_id, step, timestamp, accused, attestation_hash
 */
export function isNonParticipationAttestation(
  msg: unknown
): msg is NonParticipationAttestation {
  if (!msg || typeof msg !== 'object') return false
  const m = msg as Record<string, unknown>
  return (
    m.type === 'NON_PARTICIPATION_ATTESTATION' &&
    typeof m.channel_id === 'string' &&
    m.channel_id.length > 0 &&
    typeof m.step === 'number' &&
    m.step >= 0 &&
    Number.isInteger(m.step) &&
    typeof m.timestamp === 'number' &&
    typeof m.accused === 'string' &&
    m.accused.length > 0 &&
    typeof m.attestation_hash === 'string' &&
    /^[0-9a-f]{64}$/i.test(m.attestation_hash)
  )
}

/**
 * Check if value is any valid StateChannelMessage.
 */
export function isStateChannelMessage(
  msg: unknown
): msg is StateChannelMessage {
  return (
    isCommitmentMessage(msg) ||
    isRevealMessage(msg) ||
    isNonParticipationAttestation(msg)
  )
}

// =============================================================================
// Commitment Verification
// =============================================================================

/**
 * Verify that a reveal matches its commitment.
 * CRITICAL for unanimous consensus - any mismatch is dispute evidence.
 *
 * @param commitment_hash - The original commitment hash
 * @param result - The revealed result (JSON string)
 * @param salt - The revealed salt (64-char hex)
 * @returns true if sha256(result + ":" + salt) === commitment_hash
 */
export function verifyCommitment(
  commitment_hash: string,
  result: string,
  salt: string
): boolean {
  const input = `${result}:${salt}`
  const computed = toHex(sha256(new TextEncoder().encode(input)))
  return commitment_hash.toLowerCase() === computed.toLowerCase()
}

/**
 * Check if all reveals in a set are identical.
 * Required for unanimous consensus.
 *
 * @param reveals - Map of channel_address -> RevealMessage
 * @returns true if all result fields are identical
 */
export function areRevealsUnanimous(
  reveals: Map<string, RevealMessage>
): boolean {
  if (reveals.size === 0) return false
  const values = Array.from(reveals.values())
  const first = values[0].result
  return values.every((r) => r.result === first)
}

/**
 * Extract the agreed result from unanimous reveals.
 * Returns undefined if reveals are not unanimous.
 */
export function getUnanimousResult(
  reveals: Map<string, RevealMessage>
): unknown | undefined {
  if (!areRevealsUnanimous(reveals)) return undefined
  const first = Array.from(reveals.values())[0]
  if (!first) return undefined
  return JSON.parse(first.result)
}

