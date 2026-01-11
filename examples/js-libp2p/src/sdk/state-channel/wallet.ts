/**
 * State Channel Wallet Management (40-12)
 *
 * Hot wallet creation and channel address proof generation.
 * Uses ephemeral CosmJS wallets for fast off-chain signing.
 */

import { DirectSecp256k1HdWallet } from "@cosmjs/proto-signing";
import { createOfflineSignerSigner } from "../signers";
import { createAdr36Envelope } from "../adr36";
import type { Adr36Signer } from "../types";

// =============================================================================
// Channel Wallet Types
// =============================================================================

/**
 * Ephemeral wallet for off-chain state channel signing.
 * - address: Hot wallet address (channel_address)
 * - signer: ADR-36 compatible signer for message signing
 * - mnemonic: For optional persistence/recovery
 */
export interface ChannelWallet {
  address: string;
  signer: Adr36Signer;
  mnemonic: string;
}

// =============================================================================
// Wallet Creation
// =============================================================================

/**
 * Generate a new ephemeral CosmJS wallet for state channel signing.
 * This "hot wallet" signs off-chain messages rapidly without Keplr prompts.
 *
 * @param prefix - Bech32 address prefix (default: 'dys2')
 * @returns ChannelWallet with address, signer, and mnemonic
 */
export async function createChannelWallet(
  prefix = "dys2"
): Promise<ChannelWallet> {
  const wallet = await DirectSecp256k1HdWallet.generate(24, { prefix });
  const [account] = await wallet.getAccounts();
  const signer = await createOfflineSignerSigner({ wallet });

  return {
    address: account.address,
    signer,
    mnemonic: wallet.mnemonic,
  };
}

/**
 * Restore a ChannelWallet from an existing mnemonic.
 *
 * @param mnemonic - 24-word mnemonic phrase
 * @param prefix - Bech32 address prefix (default: 'dys2')
 * @returns ChannelWallet with address, signer, and mnemonic
 */
export async function restoreChannelWallet(
  mnemonic: string,
  prefix = "dys2"
): Promise<ChannelWallet> {
  const wallet = await DirectSecp256k1HdWallet.fromMnemonic(mnemonic.trim(), {
    prefix,
  });
  const [account] = await wallet.getAccounts();
  const signer = await createOfflineSignerSigner({ wallet });

  return {
    address: account.address,
    signer,
    mnemonic: wallet.mnemonic,
  };
}

// =============================================================================
// Channel Address Proof
// =============================================================================

/**
 * Proof data structure for agree_to_channel verification.
 * Matches script.py verify_channel_address_proof expectations.
 */
interface ChannelAddressProofData {
  participant: string;
  channel_id: string;
}

/**
 * Create a signed proof linking a hot wallet (channel_address) to a
 * participant's main wallet. Used in agree_to_channel to prove control.
 *
 * The proof is an ADR-36 signed MsgArbitraryData containing:
 * - data: JSON { participant, channel_id }
 * - app_domain: "state_channel/channel_address_proof/v1"
 * - signer: channel_address (hot wallet)
 *
 * @param channelWallet - The hot wallet that will sign off-chain messages
 * @param participantAddress - The main Keplr wallet address
 * @param channelId - The channel being joined
 * @param chainId - Chain ID for ADR-36 envelope (used for context, not signature)
 * @returns JSON-stringified ADR-36 envelope as proof
 */
export async function createChannelAddressProof(
  channelWallet: ChannelWallet,
  participantAddress: string,
  channelId: string,
  chainId: string
): Promise<string> {
  const proofData: ChannelAddressProofData = {
    participant: participantAddress,
    channel_id: channelId,
  };

  const envelope = await createAdr36Envelope({
    chainId,
    topic: "state_channel/channel_address_proof/v1",
    payload: new TextEncoder().encode(JSON.stringify(proofData)),
    signer: channelWallet.signer,
    peerId: "", // Not needed for proof
  });

  return JSON.stringify(envelope);
}

/**
 * Extract proof data from a channel address proof string.
 * Useful for verification before submission.
 *
 * @param proof - JSON-stringified ADR-36 envelope
 * @returns Parsed proof data { participant, channel_id }
 */
export function parseChannelAddressProof(
  proof: string
): ChannelAddressProofData {
  const envelope = JSON.parse(proof);
  const dataStr = envelope?.body?.messages?.[0]?.data;
  if (typeof dataStr !== "string") {
    throw new Error("Invalid proof: missing data field");
  }
  return JSON.parse(dataStr);
}
