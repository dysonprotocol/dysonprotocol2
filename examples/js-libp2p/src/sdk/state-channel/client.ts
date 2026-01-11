/**
 * State Channel Client (40-12)
 *
 * High-level client for state channel participation.
 * Manages commit-reveal workflow, consensus verification, and event handling.
 */

import type {
  DysonClient,
  DysonMessage,
  DysonMessageHandler,
} from '../types'
import type {
  StateChannelMessage,
  CommitmentMessage,
  RevealMessage,
  NonParticipationAttestation,
  LocalChannelState,
  ChannelConfig,
  ComputeResult,
} from './types'
import {
  createCommitmentHash,
  generateSalt,
  buildChannelTopic,
  createAttestationHash,
} from './helpers'
import {
  isCommitmentMessage,
  isRevealMessage,
  isNonParticipationAttestation,
  verifyCommitment,
} from './validation'
import { computeNextState } from './compute'
import type { ChannelWallet } from './wallet'

// =============================================================================
// Client Options
// =============================================================================

export interface StateChannelClientOptions {
  /** DysonClient instance for libp2p messaging */
  dysonClient: DysonClient
  /** Hot wallet for off-chain signing */
  channelWallet: ChannelWallet
  /** REST API URL for computation queries (e.g., "" for relative, "http://localhost:1317") */
  apiUrl: string
}

// =============================================================================
// Event Handlers
// =============================================================================

export type CommitmentHandler = (
  msg: CommitmentMessage,
  from: string
) => void

export type RevealHandler = (msg: RevealMessage, from: string) => void

export type StepCompleteHandler = (step: number, result: unknown) => void

export type DisagreementHandler = (
  step: number,
  reveals: Map<string, RevealMessage>
) => void

export type AttestationHandler = (
  msg: NonParticipationAttestation,
  from: string
) => void

// =============================================================================
// State Channel Client
// =============================================================================

/**
 * Client for participating in off-chain state channels.
 *
 * Workflow:
 * 1. join(config) - Subscribe to channel topic
 * 2. computeAndCommit() - Compute via REST, broadcast COMMITMENT
 * 3. Wait for all participants to commit
 * 4. submitReveal() - Broadcast REVEAL with result + salt
 * 5. Wait for all participants to reveal
 * 6. Verify unanimous consensus → onStepComplete or onDisagreement
 */
export class StateChannelClient {
  private readonly client: DysonClient
  private readonly wallet: ChannelWallet
  private readonly apiUrl: string
  private readonly channels = new Map<string, LocalChannelState>()
  private readonly pendingResults = new Map<
    string,
    { result: string; salt: string; resultHash: string }
  >()
  private readonly messageHandlers = new Map<string, DysonMessageHandler>()

  // Event handlers
  private commitmentHandlers: CommitmentHandler[] = []
  private revealHandlers: RevealHandler[] = []
  private stepCompleteHandlers: StepCompleteHandler[] = []
  private disagreementHandlers: DisagreementHandler[] = []
  private attestationHandlers: AttestationHandler[] = []

  constructor(options: StateChannelClientOptions) {
    this.client = options.dysonClient
    this.wallet = options.channelWallet
    this.apiUrl = options.apiUrl
  }

  // ===========================================================================
  // Channel Lifecycle
  // ===========================================================================

  /**
   * Join a state channel and subscribe to its topic.
   * Initializes local state tracking for commit-reveal workflow.
   *
   * @param config - Channel configuration from on-chain
   */
  async join(config: ChannelConfig): Promise<void> {
    const topic = buildChannelTopic(this.client.topicPrefix, config.channel_id)

    // Initialize local state
    const state: LocalChannelState = {
      config,
      step: 0,
      current_state: config.initial_state ?? {},
      commitments: new Map(),
      reveals: new Map(),
    }
    this.channels.set(config.channel_id, state)

    // Create message handler for this channel
    const handler: DysonMessageHandler = (msg) =>
      this.handleMessage(config.channel_id, msg)
    this.messageHandlers.set(config.channel_id, handler)

    // Subscribe to channel topic
    await this.client.subscribe(topic, handler)
  }

  /**
   * Leave a channel and unsubscribe from its topic.
   */
  async leave(channelId: string): Promise<void> {
    const topic = buildChannelTopic(this.client.topicPrefix, channelId)
    const handler = this.messageHandlers.get(channelId)

    if (handler) {
      await this.client.unsubscribe(topic, handler)
      this.messageHandlers.delete(channelId)
    }

    this.channels.delete(channelId)
    this.pendingResults.delete(channelId)
  }

  // ===========================================================================
  // Commit-Reveal Workflow
  // ===========================================================================

  /**
   * Compute next state via REST API and broadcast COMMITMENT.
   * Stores result and salt for subsequent reveal.
   *
   * @param channelId - Channel to commit to
   * @returns Computation result for display
   */
  async computeAndCommit(channelId: string): Promise<ComputeResult> {
    const state = this.channels.get(channelId)
    if (!state) {
      throw new Error(`Not joined to channel: ${channelId}`)
    }

    // Query REST API for deterministic computation
    const computed = await computeNextState(
      this.apiUrl,
      state.config,
      state.current_state,
      state.step
    )

    const result = JSON.stringify(computed.result)
    const salt = generateSalt()
    const commitment_hash = createCommitmentHash(result, salt)

    // Store for reveal phase
    this.pendingResults.set(channelId, {
      result,
      salt,
      resultHash: computed.result_hash,
    })

    const msg: CommitmentMessage = {
      type: 'COMMITMENT',
      channel_id: channelId,
      step: state.step,
      timestamp: Date.now(),
      commitment_hash,
    }

    const topic = buildChannelTopic(this.client.topicPrefix, channelId)
    await this.client.publish({
      topic,
      payload: new TextEncoder().encode(JSON.stringify(msg)),
      signer: this.wallet.signer,
    })

    return computed
  }

  /**
   * Broadcast REVEAL with previously computed result and salt.
   * Call after all participants have committed.
   *
   * @param channelId - Channel to reveal in
   */
  async submitReveal(channelId: string): Promise<void> {
    const state = this.channels.get(channelId)
    if (!state) {
      throw new Error(`Not joined to channel: ${channelId}`)
    }

    const pending = this.pendingResults.get(channelId)
    if (!pending) {
      throw new Error(`No pending commitment for channel: ${channelId}`)
    }

    const msg: RevealMessage = {
      type: 'REVEAL',
      channel_id: channelId,
      step: state.step,
      timestamp: Date.now(),
      result: pending.result,
      salt: pending.salt,
    }

    const topic = buildChannelTopic(this.client.topicPrefix, channelId)
    await this.client.publish({
      topic,
      payload: new TextEncoder().encode(JSON.stringify(msg)),
      signer: this.wallet.signer,
    })
  }

  // ===========================================================================
  // Non-Participation Attestation
  // ===========================================================================

  /**
   * Create a signed attestation for a non-participating member.
   * Collect quorum attestations off-chain, then submit on-chain.
   *
   * @param channelId - Channel ID
   * @param accused - Address of non-participating member
   * @param step - Step where non-participation occurred
   * @returns Attestation message (not yet broadcast)
   */
  createAttestation(
    channelId: string,
    accused: string,
    step: number
  ): NonParticipationAttestation {
    const timestamp = Date.now()
    const attestation_hash = createAttestationHash(
      accused,
      channelId,
      step,
      timestamp
    )

    return {
      type: 'NON_PARTICIPATION_ATTESTATION',
      channel_id: channelId,
      step,
      timestamp,
      accused,
      attestation_hash,
    }
  }

  /**
   * Broadcast a non-participation attestation.
   */
  async broadcastAttestation(
    attestation: NonParticipationAttestation
  ): Promise<void> {
    const topic = buildChannelTopic(
      this.client.topicPrefix,
      attestation.channel_id
    )
    await this.client.publish({
      topic,
      payload: new TextEncoder().encode(JSON.stringify(attestation)),
      signer: this.wallet.signer,
    })
  }

  // ===========================================================================
  // Event Handler Registration
  // ===========================================================================

  onCommitment(handler: CommitmentHandler): void {
    this.commitmentHandlers.push(handler)
  }

  onReveal(handler: RevealHandler): void {
    this.revealHandlers.push(handler)
  }

  onStepComplete(handler: StepCompleteHandler): void {
    this.stepCompleteHandlers.push(handler)
  }

  onDisagreement(handler: DisagreementHandler): void {
    this.disagreementHandlers.push(handler)
  }

  onAttestation(handler: AttestationHandler): void {
    this.attestationHandlers.push(handler)
  }

  // ===========================================================================
  // State Access
  // ===========================================================================

  getChannelState(channelId: string): LocalChannelState | undefined {
    return this.channels.get(channelId)
  }

  getChannelAddress(): string {
    return this.wallet.address
  }

  /**
   * Check if all participants have committed for current step.
   */
  allCommitted(channelId: string): boolean {
    const state = this.channels.get(channelId)
    if (!state) return false
    return state.commitments.size === state.config.participants.length
  }

  /**
   * Check if all participants have revealed for current step.
   */
  allRevealed(channelId: string): boolean {
    const state = this.channels.get(channelId)
    if (!state) return false
    return state.reveals.size === state.config.participants.length
  }

  // ===========================================================================
  // Internal Message Handling
  // ===========================================================================

  private handleMessage(channelId: string, msg: DysonMessage): void {
    if (!msg.payloadJson) return

    const scMsg = msg.payloadJson as StateChannelMessage
    if (scMsg.channel_id !== channelId) return

    const from = this.extractSignerAddress(msg)

    if (isCommitmentMessage(scMsg)) {
      this.handleCommitment(channelId, scMsg, from)
    } else if (isRevealMessage(scMsg)) {
      this.handleReveal(channelId, scMsg, from)
    } else if (isNonParticipationAttestation(scMsg)) {
      this.handleAttestation(channelId, scMsg, from)
    }
  }

  private handleCommitment(
    channelId: string,
    msg: CommitmentMessage,
    from: string
  ): void {
    const state = this.channels.get(channelId)
    if (!state || msg.step !== state.step) return

    state.commitments.set(from, msg)
    this.commitmentHandlers.forEach((h) => h(msg, from))
  }

  private handleReveal(
    channelId: string,
    msg: RevealMessage,
    from: string
  ): void {
    const state = this.channels.get(channelId)
    if (!state || msg.step !== state.step) return

    // Verify reveal matches commitment
    const commitment = state.commitments.get(from)
    if (
      commitment &&
      !verifyCommitment(commitment.commitment_hash, msg.result, msg.salt)
    ) {
      console.warn(
        `[state-channel] Commitment mismatch from ${from} - dispute evidence`
      )
      // This is dispute evidence - commitment doesn't match reveal
    }

    state.reveals.set(from, msg)
    this.revealHandlers.forEach((h) => h(msg, from))

    this.checkStepProgress(channelId)
  }

  private handleAttestation(
    channelId: string,
    msg: NonParticipationAttestation,
    from: string
  ): void {
    this.attestationHandlers.forEach((h) => h(msg, from))
  }

  private checkStepProgress(channelId: string): void {
    const state = this.channels.get(channelId)
    if (!state) return

    const n = state.config.participants.length

    // Check if ALL participants have revealed (unanimous requirement)
    if (state.reveals.size !== n) return

    // Verify ALL reveals are identical (unanimous consensus)
    const reveals = Array.from(state.reveals.values())
    const firstResult = reveals[0].result
    const allMatch = reveals.every((r) => r.result === firstResult)

    if (allMatch) {
      // Unanimous agreement - advance step
      const result = JSON.parse(firstResult)
      const completedStep = state.step

      state.current_state = result
      state.step++
      state.commitments.clear()
      state.reveals.clear()
      this.pendingResults.delete(channelId)

      this.stepCompleteHandlers.forEach((h) => h(completedStep, result))
    } else {
      // Disagreement - trigger dispute handlers
      console.warn(
        `[state-channel] Disagreement at step ${state.step} - dispute required`
      )
      this.disagreementHandlers.forEach((h) =>
        h(state.step, new Map(state.reveals))
      )
    }
  }

  private extractSignerAddress(msg: DysonMessage): string {
    return msg.envelope?.body?.messages?.[0]?.signer ?? ''
  }
}

// =============================================================================
// Factory Function
// =============================================================================

/**
 * Create a StateChannelClient instance.
 *
 * @param options - Client configuration
 * @returns StateChannelClient ready for use
 */
export function createStateChannelClient(
  options: StateChannelClientOptions
): StateChannelClient {
  return new StateChannelClient(options)
}

