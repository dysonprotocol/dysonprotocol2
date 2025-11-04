import { createLibp2p, Libp2p } from 'libp2p'
import { gossipsub } from '@chainsafe/libp2p-gossipsub'
import { noise } from '@chainsafe/libp2p-noise'
import { yamux } from '@chainsafe/libp2p-yamux'
import { identify } from '@libp2p/identify'
import { circuitRelayTransport } from '@libp2p/circuit-relay-v2'
import { webSockets } from '@libp2p/websockets'
import { webTransport } from '@libp2p/webtransport'
import { webRTC, webRTCDirect } from '@libp2p/webrtc'
import { pubsubPeerDiscovery } from '@libp2p/pubsub-peer-discovery'
import { GossipLog as IndexedDBGossipLog } from '@canvas-js/gossiplog/idb'
import { gossipLogService } from '@canvas-js/gossiplog/libp2p'
import { multiaddr, Multiaddr } from '@multiformats/multiaddr'
import { fromString as uint8FromString } from 'uint8arrays/from-string'
import { toString as uint8ToString } from 'uint8arrays/to-string'
import type { PeerId } from '@libp2p/interface'

import { createAdr36Envelope } from './adr36'
import type {
    Adr36Signer,
    Adr36Envelope,
    BootstrapInfo,
    CreateDysonClientOptions,
    DysonClient,
    DysonMessage,
    DysonMessageHandler,
    PublishJsonParams,
    PublishParams,
} from './types'

const textDecoder = new TextDecoder()

interface TopicRegistryEntry {
    handlers: Set<DysonMessageHandler>
}

interface DysonLogPayload {
    topic: string
    data: string
    from?: string
}

function isDysonLogPayload(payload: unknown): payload is DysonLogPayload {
    if (typeof payload !== 'object' || payload === null) {
        return false
    }
    const record = payload as Record<string, unknown>
    return (
        typeof record.topic === 'string' &&
        typeof record.data === 'string' &&
        (record.from === undefined || typeof record.from === 'string')
    )
}

const MIN_BROWSER_BACKOFF_MS = 1000
const MAX_BROWSER_BACKOFF_MS = 120_000
const BROWSER_PEER_TAG = 'browser-mesh'

interface PeerConnectionState {
    timer?: ReturnType<typeof setTimeout>
    backoffMs: number
}

class DysonClientImpl implements DysonClient {
    readonly libp2p: Libp2p
    readonly bootstrap: BootstrapInfo
    readonly chainId: string
    readonly topicPrefix: string
    readonly peerId: string
    readonly discoveryTopic: string
    readonly gossipLog: IndexedDBGossipLog<DysonLogPayload>

    private readonly pubsub: any
    private readonly topics = new Map<string, TopicRegistryEntry>()
    private readonly peerState = new Map<string, PeerConnectionState>()
    private readonly onPeerDiscovery: (evt: CustomEvent<any>) => void
    private readonly onPeerConnect: (evt: CustomEvent<any>) => void
    private readonly onPeerDisconnect: (evt: CustomEvent<any>) => void
    private discoveryInterval?: ReturnType<typeof setInterval>

    constructor(libp2p: Libp2p, bootstrap: BootstrapInfo, discoveryTopic: string, gossipLog: IndexedDBGossipLog<DysonLogPayload>) {
        this.libp2p = libp2p
        this.bootstrap = bootstrap
        this.chainId = bootstrap.chainId
        this.topicPrefix = bootstrap.topicPrefix.endsWith('/') ? bootstrap.topicPrefix : `${bootstrap.topicPrefix}/`
        this.peerId = libp2p.peerId.toString()
        this.discoveryTopic = discoveryTopic
        this.gossipLog = gossipLog
        this.pubsub = libp2p.services.pubsub

        this.onPeerDiscovery = (evt: CustomEvent<any>) => {
            const info = evt?.detail
            if (!info?.id) return

            const peerId = info.id as PeerId
            const multiaddrs: Multiaddr[] = info.multiaddrs ?? []

            this.storeKnownAddrs(peerId, multiaddrs)
            void this.dialPeer(peerId, 'discovery', multiaddrs)
        }

        this.onPeerConnect = (evt: CustomEvent<any>) => {
            const detail = evt?.detail
            const peerId: PeerId | undefined = detail?.remotePeer
            if (!peerId) return

            this.clearPeerTimer(peerId.toString())
            this.peerState.set(peerId.toString(), { backoffMs: MIN_BROWSER_BACKOFF_MS })

            const cm = this.getConnectionManager()
            if (cm?.protect) {
                cm.protect(peerId, BROWSER_PEER_TAG)
            }

            this.storeKnownAddrs(peerId, detail?.remoteAddr ? [detail.remoteAddr] : [])
        }

        this.onPeerDisconnect = (evt: CustomEvent<any>) => {
            const detail = evt?.detail
            const peerId: PeerId | undefined = detail?.remotePeer
            if (!peerId) return

            this.scheduleRedial(peerId, 'disconnect')
        }

        libp2p.addEventListener('peer:discovery', this.onPeerDiscovery)
        libp2p.addEventListener('peer:connect', this.onPeerConnect)
        libp2p.addEventListener('peer:disconnect', this.onPeerDisconnect)

        this.gossipLog.setConsumer(async (signedMessage) => {
            const payload = signedMessage.message.payload
            if (isDysonLogPayload(payload)) {
                this.dispatchLogPayload(payload)
            }
            return undefined
        })

        this.discoveryInterval = setInterval(() => this.publishPresence('heartbeat'), 30_000)
        this.publishPresence('startup')
    }

    buildTopic(root: string, suffix = ''): string {
        const sanitizedRoot = root.trim()
        const sanitizedSuffix = suffix.trim()
        const base = `${this.topicPrefix}${sanitizedRoot}`
        return sanitizedSuffix ? `${base}/${sanitizedSuffix}` : base
    }

    async subscribe(topic: string, handler: DysonMessageHandler): Promise<void> {
        const normalisedTopic = topic.trim()
        if (!normalisedTopic) {
            throw new Error('Topic cannot be empty')
        }
        console.log(`[dyson-sdk] subscribe(): topic=${normalisedTopic}`)
        let entry = this.topics.get(normalisedTopic)
        if (!entry) {
            console.log(`[dyson-sdk] calling pubsub.subscribe(${normalisedTopic})...`)
            console.log(`[dyson-sdk] pubsub peers before subscribe:`, this.pubsub.getPeers())
            this.pubsub.subscribe(normalisedTopic)
            console.log(`[dyson-sdk] pubsub.subscribe() returned`)
            console.log(`[dyson-sdk] pubsub topic peers:`, this.pubsub.getSubscribers(normalisedTopic))
            entry = {
                handlers: new Set(),
            }
            this.topics.set(normalisedTopic, entry)
        }
        entry.handlers.add(handler)
        await this.replayForHandler(normalisedTopic, handler)
    }

    async subscribeSuffix(root: string, suffix: string, handler: DysonMessageHandler): Promise<string> {
        const topic = this.buildTopic(root, suffix)
        await this.subscribe(topic, handler)
        return topic
    }

    async unsubscribe(topic: string, handler?: DysonMessageHandler): Promise<void> {
        const entry = this.topics.get(topic)
        if (!entry) return
        if (handler) {
            entry.handlers.delete(handler)
        }
        if (!handler || entry.handlers.size === 0) {
            try {
                await this.pubsub.unsubscribe(topic)
            } catch (err) {
                console.warn('Dyson unsubscribe error', err)
            }
            this.topics.delete(topic)
        }
    }

    async publish(params: PublishParams): Promise<void> {
        const { topic, payload, signer, peerId } = params
        const envelope = await createAdr36Envelope({
            chainId: this.chainId,
            topic,
            payload,
            signer,
            peerId: peerId ?? this.peerId,
        })
        const envelopeJson = JSON.stringify(envelope)
        const payloadBytes = uint8FromString(envelopeJson)
        const logPayload: DysonLogPayload = {
            topic,
            data: envelopeJson,
            from: this.peerId,
        }
        await this.gossipLog.append(logPayload)
    }

    async publishJson(params: PublishJsonParams): Promise<void> {
        const { root, suffix, data, signer, peerId } = params
        const topic = this.buildTopic(root, suffix)
        const payloadBytes = uint8FromString(JSON.stringify(data))
        await this.publish({ topic, payload: payloadBytes, signer, peerId })
    }

    async stop(): Promise<void> {
        for (const [topic, entry] of this.topics.entries()) {
            try {
                await this.pubsub.unsubscribe(topic)
            } catch (err) {
                console.warn('Dyson unsubscribe error on stop', err)
            }
        }
        this.topics.clear()

        this.libp2p.removeEventListener('peer:discovery', this.onPeerDiscovery)
        this.libp2p.removeEventListener('peer:connect', this.onPeerConnect)
        this.libp2p.removeEventListener('peer:disconnect', this.onPeerDisconnect)

        if (this.discoveryInterval) {
            clearInterval(this.discoveryInterval)
            this.discoveryInterval = undefined
        }

        for (const state of this.peerState.values()) {
            if (state.timer) {
                clearTimeout(state.timer)
            }
        }
        this.peerState.clear()

        await this.libp2p.stop()
        await this.gossipLog.close()
    }

    private getConnectionManager(): any {
        return (this.libp2p as any).connectionManager
    }

    private getAddressBook(): any {
        const peerStore = (this.libp2p as any).peerStore
        return peerStore?.addressBook
    }

    private storeKnownAddrs(peerId: PeerId, addrs: Multiaddr[]): void {
        if (!addrs || addrs.length === 0) {
            return
        }

        const addressBook = this.getAddressBook()
        if (!addressBook) {
            return
        }

        try {
            if (typeof addressBook.add === 'function') {
                addressBook.add(peerId, addrs)
            } else if (typeof addressBook.set === 'function') {
                addressBook.set(peerId, addrs)
            }
        } catch (err) {
            console.warn('[dyson-sdk] failed to store peer addrs', err)
        }
    }

    private async dialPeer(peerId: PeerId, reason: string, discoveredAddrs: Multiaddr[] = []): Promise<void> {
        if (this.libp2p.getConnections(peerId).length > 0) {
            return
        }

        let storedAddrs: Multiaddr[] = []
        try {
            const addressBook = this.getAddressBook()
            storedAddrs = (addressBook?.get?.(peerId) ?? []) as Multiaddr[]
        } catch (err) {
            console.warn('[dyson-sdk] failed to read peer addrs', err)
        }
        const candidateAddrs = [...discoveredAddrs, ...storedAddrs]

        const preferred = candidateAddrs.filter((addr) => addr.protoNames().includes('webrtc') && addr.protoNames().includes('p2p-circuit'))
        const fallbacks = candidateAddrs.filter((addr) => !preferred.includes(addr))
        const targets = preferred.length > 0 ? preferred : fallbacks

        for (const addr of targets) {
            try {
                console.log(`[dyson-sdk] dialing ${addr.toString()} (${reason})`)
                const conn = await this.libp2p.dial(addr)
                console.log(`[dyson-sdk] browser mesh connected ${conn.remotePeer}`)
                this.peerState.set(peerId.toString(), { backoffMs: MIN_BROWSER_BACKOFF_MS })
                const cm = this.getConnectionManager()
                if (cm?.protect) {
                    cm.protect(peerId, BROWSER_PEER_TAG)
                }
                return
            } catch (err) {
                console.warn('[dyson-sdk] dial failed', addr.toString(), err)
            }
        }

        try {
            await this.libp2p.dial(peerId)
            this.peerState.set(peerId.toString(), { backoffMs: MIN_BROWSER_BACKOFF_MS })
            const cm = this.getConnectionManager()
            if (cm?.protect) {
                cm.protect(peerId, BROWSER_PEER_TAG)
            }
            return
        } catch (err) {
            console.warn('[dyson-sdk] peer dial failed', peerId.toString(), err)
        }

        this.scheduleRedial(peerId, `dial-failed:${reason}`)
    }

    private scheduleRedial(peerId: PeerId, reason: string): void {
        const id = peerId.toString()
        let state = this.peerState.get(id)
        if (!state) {
            state = { backoffMs: MIN_BROWSER_BACKOFF_MS }
            this.peerState.set(id, state)
        }

        this.clearPeerTimer(id)

        const jitter = Math.max(state.backoffMs * 0.5, 1000)
        const delay = state.backoffMs + Math.floor(Math.random() * jitter)

        state.timer = setTimeout(() => {
            state!.timer = undefined
            void this.dialPeer(peerId, reason)
        }, delay)

        state.backoffMs = Math.min(state.backoffMs * 2, MAX_BROWSER_BACKOFF_MS)
        console.log(`[dyson-sdk] scheduled reconnect to ${id} in ~${delay}ms (${reason})`)
    }

    private clearPeerTimer(id: string): void {
        const state = this.peerState.get(id)
        if (!state?.timer) {
            return
        }
        clearTimeout(state.timer)
        state.timer = undefined
    }

    private dispatchLogPayload(payload: DysonLogPayload): void {
        const entry = this.topics.get(payload.topic)
        if (!entry) {
            return
        }

        const message = this.buildMessageFromPayload(payload)
        if (!message) {
            return
        }

        for (const handler of entry.handlers) {
            try {
                handler(message)
            } catch (err) {
                console.error('Dyson handler error', err)
            }
        }
    }

    private buildMessageFromPayload(payload: DysonLogPayload): DysonMessage | null {
        try {
            const envelope = JSON.parse(payload.data)
            const bytes = uint8FromString(JSON.stringify(envelope))
            return decodeMessage({
                data: bytes,
                topic: payload.topic,
                from: payload.from ?? this.peerId,
            }, payload.topic)
        } catch (err) {
            console.warn('[dyson-sdk] failed to decode message from gossiplog payload', err)
            return null
        }
    }

    private async replayForHandler(topic: string, handler: DysonMessageHandler): Promise<void> {
        for await (const signedMessage of this.gossipLog.iterate()) {
            const payload = signedMessage.message.payload
            if (!isDysonLogPayload(payload) || payload.topic !== topic) {
                continue
            }

            const message = this.buildMessageFromPayload(payload)
            if (!message) {
                continue
            }

            try {
                handler(message)
            } catch (err) {
                console.error('Dyson handler error during replay', err)
            }
        }
    }

    private publishPresence(reason: string): void {
        const addrs = this.libp2p.getMultiaddrs().map((addr) => addr.toString())
        const payload = {
            peer: this.peerId,
            addrs,
            reason,
            ts: Date.now(),
        }

        void this.pubsub.publish(this.discoveryTopic, uint8FromString(JSON.stringify(payload))).catch((err: unknown) => {
            console.warn('[dyson-sdk] discovery publish failed', err)
        })
    }
}

export async function createDysonClient(options: CreateDysonClientOptions = {}): Promise<DysonClient> {
    const bootstrapUrl = options.bootstrapUrl ?? '/libp2p/bootstrap'
    const fetchFn = options.fetchFn ?? globalThis.fetch
    if (!fetchFn) {
        throw new Error('No fetch implementation available')
    }

    const res = await fetchFn(bootstrapUrl)
    if (!res.ok) {
        throw new Error(`Bootstrap request failed: ${res.status}`)
    }
    const bootstrap = (await res.json()) as BootstrapInfo

    const topicPrefix = bootstrap.topicPrefix.endsWith('/') ? bootstrap.topicPrefix : `${bootstrap.topicPrefix}/`
    const discoveryTopic = `${topicPrefix}discovery`
    const relayListenAddrs = bootstrap.relayListenAddrs ?? []
    const gossipLogTopic = `${bootstrap.chainId}-gossiplog`

    const gossipLog = await IndexedDBGossipLog.open<DysonLogPayload>({
        topic: gossipLogTopic,
        apply: async () => undefined,
        validatePayload: isDysonLogPayload,
    })

    console.log(`[dyson-sdk] chainID: ${bootstrap.chainId}`)
    console.log(`[dyson-sdk] relay listen addrs: ${relayListenAddrs.length}`)

    const node = await createLibp2p({
        addresses: {
            listen: [
                '/webrtc',  // Listen for browser-to-browser WebRTC
                ...relayListenAddrs,  // Listen on relay addresses
            ],
        },
        transports: [
            webTransport(),
            webSockets(),
            webRTC({
                rtcConfiguration: {
                    iceServers: bootstrap.ice?.servers ?? [
                        { urls: ['stun:stun.l.google.com:19302'] }
                    ]
                }
            }),
            webRTCDirect(),
            circuitRelayTransport({
                discoverRelays: 1,  // Discover at least 1 relay
            } as any)
        ],
        connectionEncrypters: [noise()],
        streamMuxers: [yamux()],
        connectionGater: {
            denyDialMultiaddr: async () => false,
        },
        peerDiscovery: [
            // PubSub peer discovery for local and cross-domain discovery
            // Works via GossipSub mesh - peers propagate discovery messages
            pubsubPeerDiscovery({
                interval: 10_000,
                topics: [discoveryTopic],
                listenOnly: false,
            }),
        ],
        services: {
            identify: identify(),
            pubsub: gossipsub({
                emitSelf: true,
                allowPublishToZeroTopicPeers: true
            }),
            gossipLog: gossipLogService<DysonLogPayload>({ gossipLog }),
        },
    })

    console.log(`[dyson-sdk] created libp2p peerId=${node.peerId.toString()}`)

    // Start the node
    await node.start()
    console.log(`[dyson-sdk] node started`)

    // Subscribe to discovery topic BEFORE dialing
    node.services.pubsub.subscribe(discoveryTopic)
    console.log(`[dyson-sdk] pre-subscribed to discovery topic: ${discoveryTopic}`)

    // Dial bootstrap server(s) and wait for relay reservation
    let connected = false
    for (const addr of bootstrap.addrs ?? []) {
        if (connected) break
        try {
            console.log(`[dyson-sdk] dialing ${addr}...`)
            const conn = await node.dial(multiaddr(addr))
            console.log(`[dyson-sdk] connected to ${conn.remotePeer} via ${conn.remoteAddr}`)

            // Wait for identify to complete
            await waitForIdentify(node, conn.remotePeer)

            // Wait for relay reservation
            await waitForRelayReservation(node)

            connected = true
        } catch (err) {
            console.warn('[dyson-sdk] dial failed', addr, err)
        }
    }

    if (!connected) {
        console.warn('[dyson-sdk] no successful connections to bootstrap peers')
    }

    // Log addresses
    const myAddrs = node.getMultiaddrs()
    const relayAddrs = myAddrs.filter(ma =>
        ma.protoNames().includes('p2p-circuit') && ma.protoNames().includes('webrtc')
    )
    console.log('[dyson-sdk] my relay addresses:', relayAddrs.map(a => a.toString()))

    return new DysonClientImpl(node, bootstrap, discoveryTopic, gossipLog)
}

async function waitForIdentify(node: Libp2p, peerId: PeerId, timeoutMs = 1000): Promise<void> {
    const identifyService = (node.services as any)?.identify
    if (identifyService?.identifyPeer) {
        try {
            await identifyService.identifyPeer(peerId)
            console.log(`[dyson-sdk] identified peer ${peerId}`)
            return
        } catch (err) {
            console.warn(`[dyson-sdk] identifyPeer call failed for ${peerId}:`, err)
        }
    }

    const signal = createTimeoutSignal(timeoutMs)

    await new Promise<void>((resolve) => {
        let settled = false
        const cleanup = () => {
            if (settled) return
            settled = true
            node.removeEventListener('peer:identify', onIdentify)
            signal?.removeEventListener('abort', onAbort)
            resolve()
        }
        const onIdentify = (evt: any) => {
            if (evt?.detail?.peerId?.toString() === peerId.toString()) {
                console.log(`[dyson-sdk] identified peer ${peerId}`)
                cleanup()
            }
        }
        const onAbort = () => {
            console.warn(`[dyson-sdk] identify wait timed out for ${peerId}`)
            cleanup()
        }

        node.addEventListener('peer:identify', onIdentify)
        if (signal) {
            signal.addEventListener('abort', onAbort, { once: true })
        }
    })
}

async function waitForRelayReservation(node: Libp2p, timeoutMs = 5000): Promise<void> {
    const hasReservation = () => node.getMultiaddrs().some(ma => ma.protoNames().includes('p2p-circuit'))
    if (hasReservation()) {
        return
    }

    const signal = createTimeoutSignal(timeoutMs)

    await new Promise<void>((resolve) => {
        let settled = false
        const cleanup = () => {
            if (settled) return
            settled = true
            node.removeEventListener('self:peer:update', onSelfPeerUpdate)
            signal?.removeEventListener('abort', onAbort)
            resolve()
        }
        const onSelfPeerUpdate = () => {
            if (hasReservation()) {
                console.log('[dyson-sdk] relay reservation created')
                cleanup()
            }
        }
        const onAbort = () => {
            console.warn('[dyson-sdk] relay reservation wait timed out')
            cleanup()
        }

        node.addEventListener('self:peer:update', onSelfPeerUpdate)
        if (signal) {
            signal.addEventListener('abort', onAbort, { once: true })
        }

        // In case the reservation was created between our initial check and listener registration
        onSelfPeerUpdate()
    })
}

function createTimeoutSignal(timeoutMs: number) {
    if (typeof timeoutMs !== 'number' || timeoutMs <= 0) {
        return undefined
    }
    if (typeof AbortSignal !== 'undefined' && typeof (AbortSignal as any).timeout === 'function') {
        return (AbortSignal as any).timeout(timeoutMs) as AbortSignal
    }
    return undefined
}

function decodeMessage(detail: any, topic: string): DysonMessage {
    const raw: Uint8Array = detail.data instanceof Uint8Array ? detail.data : new Uint8Array(detail.data ?? [])

    let envelope: Adr36Envelope | null = null
    let payload = new Uint8Array()
    let payloadJson: unknown

    try {
        envelope = JSON.parse(uint8ToString(raw)) as Adr36Envelope
        const tx = JSON.parse(envelope.adr36_tx_json)
        const msg = tx?.body?.messages?.[0]
        const dataStr = msg?.data
        if (typeof dataStr === 'string' && dataStr.length > 0) {
            try {
                const parsed = JSON.parse(dataStr)
                if (parsed && typeof parsed === 'object') {
                    const cloned: Record<string, unknown> = { ...parsed }
                    delete cloned.peerId
                    payloadJson = cloned
                    payload = Uint8Array.from(uint8FromString(JSON.stringify(cloned)))
                } else {
                    payloadJson = parsed
                    payload = Uint8Array.from(uint8FromString(JSON.stringify(parsed)))
                }
            } catch {
                payload = Uint8Array.from(uint8FromString(dataStr))
            }
        }
    } catch (err) {
        console.warn('Dyson decode error', err)
    }

    return {
        topic,
        from: detail.from,
        envelope,
        payload,
        payloadJson,
        raw,
    }
}


