import type { Libp2p } from 'libp2p'
import type { SignDoc } from '@cosmjs/proto-signing'

export interface BootstrapInfo {
    peerId: string
    addrs: string[]
    relayListenAddrs?: string[]
    rendezvous: string
    rendezvousAddrs?: string[]
    bootstrapPeers?: string[] // Known peers in the network
    topicPrefix: string
    version: string
    ice?: {
        servers?: Array<{
            urls: string[]
            username?: string
            credential?: string
        }>
    }
}

export interface SignResult {
    signed: SignDoc
    signatureBase64: string
}

export interface Adr36Signer {
    readonly address: string
    readonly pubkeyBase64: string
    sign(signDoc: SignDoc): Promise<SignResult>
}

export interface Adr36Envelope {
    adr36_tx_json: string
    v: number
}

export interface DysonMessage {
    topic: string
    from: string
    envelope: Adr36Envelope | null
    payload: Uint8Array
    payloadJson?: unknown
    raw: Uint8Array
}

export type DysonMessageHandler = (message: DysonMessage) => void

export interface PublishParams {
    topic: string
    payload: Uint8Array
    signer: Adr36Signer
    peerId?: string
}

export interface PublishJsonParams {
    root: string
    suffix: string
    data: unknown
    signer: Adr36Signer
    peerId?: string
}

export interface CreateDysonClientOptions {
    bootstrapUrl?: string
    fetchFn?: typeof fetch
}

export interface DysonClient {
    readonly libp2p: Libp2p
    readonly bootstrap: BootstrapInfo
    readonly chainId: string
    readonly topicPrefix: string
    readonly peerId: string

    buildTopic(root: string, suffix?: string): string
    subscribe(topic: string, handler: DysonMessageHandler): Promise<void>
    subscribeSuffix(root: string, suffix: string, handler: DysonMessageHandler): Promise<string>
    unsubscribe(topic: string, handler?: DysonMessageHandler): Promise<void>
    publish(params: PublishParams): Promise<void>
    publishJson(params: PublishJsonParams): Promise<void>
    stop(): Promise<void>
}

