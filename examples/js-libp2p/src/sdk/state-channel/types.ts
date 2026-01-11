/**
 * State Channel Protocol Types (40-11)
 *
 * Message type definitions for off-chain state channel communication
 * over libp2p GossipSub. Designed for unanimous consensus where all
 * participants must agree on each step result.
 */

// =============================================================================
// Message Type Enum
// =============================================================================

export const StateChannelMessageType = {
  COMMITMENT: 'COMMITMENT',
  REVEAL: 'REVEAL',
  NON_PARTICIPATION_ATTESTATION: 'NON_PARTICIPATION_ATTESTATION',
} as const

export type StateChannelMessageTypeValue =
  (typeof StateChannelMessageType)[keyof typeof StateChannelMessageType]

// =============================================================================
// Message Interfaces
// =============================================================================

/**
 * Base message structure embedded in MsgArbitraryData.data field
 */
export interface BaseStateChannelMessage {
  type: StateChannelMessageTypeValue
  channel_id: string
  step: number
  timestamp: number
}

/**
 * Commitment message: sha256(result_json + ":" + salt)
 * Broadcast during commitment phase before revealing result.
 */
export interface CommitmentMessage extends BaseStateChannelMessage {
  type: 'COMMITMENT'
  commitment_hash: string // 64-char hex sha256
}

/**
 * Reveal message: exposes result and salt to verify commitment.
 * All participants must reveal identical results for step to advance.
 */
export interface RevealMessage extends BaseStateChannelMessage {
  type: 'REVEAL'
  result: string // JSON-stringified computation result
  salt: string // Random 64-char hex used in commitment
}

/**
 * Non-participation attestation: signed claim that a participant
 * failed to respond within timeout. Collected for quorum-based
 * non-participation proof submission on-chain.
 */
export interface NonParticipationAttestation extends BaseStateChannelMessage {
  type: 'NON_PARTICIPATION_ATTESTATION'
  accused: string // Address of non-participating member
  attestation_hash: string // Deterministic hash of accusation data
}

export type StateChannelMessage =
  | CommitmentMessage
  | RevealMessage
  | NonParticipationAttestation

// =============================================================================
// Channel Configuration & State
// =============================================================================

/**
 * Participant in a channel with dual address scheme:
 * - address: Main Keplr wallet (cold) - holds escrow
 * - channel_address: Hot wallet for off-chain signing
 */
export interface ChannelParticipant {
  address: string
  channel_address: string
}

/**
 * Channel configuration from on-chain storage.
 * Immutable after creation.
 */
export interface ChannelConfig {
  channel_id: string
  script_address: string
  computation_script: string
  participants: ChannelParticipant[]
  total_steps: number
  escrow_per_participant: number
  commitment_timeout: number // seconds
  reveal_timeout: number // seconds
  initial_state: unknown
}

/**
 * Local client-side channel state tracking.
 * Ephemeral - not persisted on-chain.
 */
export interface LocalChannelState {
  config: ChannelConfig
  step: number
  current_state: unknown
  commitments: Map<string, CommitmentMessage> // channel_address -> commitment
  reveals: Map<string, RevealMessage> // channel_address -> reveal
}

// =============================================================================
// Computation Result
// =============================================================================

/**
 * Result from execute_computation REST API query.
 */
export interface ComputeResult {
  result: unknown
  result_hash: string
}

// =============================================================================
// Step Phase Tracking
// =============================================================================

export const StepPhase = {
  COMPUTING: 'computing',
  COMMITTING: 'committing',
  REVEALING: 'revealing',
  VERIFYING: 'verifying',
  COMPLETE: 'complete',
  DISPUTED: 'disputed',
} as const

export type StepPhaseValue = (typeof StepPhase)[keyof typeof StepPhase]

