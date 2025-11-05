import type { Libp2p } from 'libp2p'
import type { SignDoc } from 'cosmjs-types/cosmos/tx/v1beta1/tx'

export interface BootstrapInfo {
    peerId: string
    addrs: string[]
    relayListenAddrs?: string[]
    chainId: string
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

export interface MsgArbitraryData {
    body: {
        messages: Array<{
            '@type': string
            signer: string
            data: string
            app_domain: string
            metadata: string
        }>
        memo: string
        timeout_height: string
    }
    auth_info: {
        signer_infos: Array<{
            public_key: {
                '@type': string
                key: string
            }
            mode_info: {
                single: { mode: string }
            }
            sequence: string
        }>
        fee: {
            amount: any[]
            gas_limit: string
        }
    }
    signatures: string[]
}

export interface DysonMessage {
    topic: string
    from: string
    envelope: MsgArbitraryData | null
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

