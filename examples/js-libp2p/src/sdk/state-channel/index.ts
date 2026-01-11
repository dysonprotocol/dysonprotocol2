/**
 * State Channel SDK (40-11, 40-12)
 *
 * Off-chain state channel protocol for libp2p GossipSub.
 * Enables N-party computation with commit-reveal consensus.
 */

// Types
export * from './types'

// Message validation
export * from './validation'

// Hash and utility helpers
export * from './helpers'

// REST API computation
export * from './compute'

// Hot wallet management (40-12)
export * from './wallet'

// State channel client (40-12)
export * from './client'

