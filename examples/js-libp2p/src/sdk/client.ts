import { createLibp2p, Libp2p } from 'libp2p'
import { gossipsub } from '@chainsafe/libp2p-gossipsub'
import { noise } from '@chainsafe/libp2p-noise'
import { yamux } from '@chainsafe/libp2p-yamux'
import { identify } from '@libp2p/identify'
import { dcutr } from '@libp2p/dcutr'
import { autoNAT } from '@libp2p/autonat'
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

// no base64 for payload data; treat as UTF-8 text
import { createAdr36Envelope, verifyAdr36Envelope } from './adr36'
import type {
    Adr36Signer,
    MsgArbitraryData,
    BootstrapInfo,
    CreateDysonClientOptions,
    DysonClient,
    DysonMessage,
    DysonMessageHandler,
    PublishJsonParams,
    PublishParams,
} from './types'

const textDecoder = new TextDecoder()

const DEFAULT_MAX_ENVELOPE_BYTES = 64 * 1024
// Minimal Promise.any polyfill for ES2020 targets
async function promiseAny<T>(promises: Array<Promise<T>>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
        let pending = promises.length
        if (pending === 0) {
            reject(new Error('All promises were rejected'))
            return
        }
        let rejected = 0
        let firstError: any
        for (const p of promises) {
            p.then((v) => {
                resolve(v)
            }).catch((err) => {
                rejected++
                if (firstError === undefined) firstError = err
                if (rejected === pending) {
                    reject(firstError ?? new Error('All promises were rejected'))
                }
            })
        }
    })
}

// Track in-flight identify waits to avoid duplicate listeners per peer
const identifyInFlight = new Map<string, Promise<void>>()

function isWebsocketAddr(ma: Multiaddr): boolean {
    const protos = ma.protoNames()
    return protos.includes('ws') || protos.includes('wss') || protos.includes('tls')
}

function isWebTransportAddr(ma: Multiaddr): boolean {
    const protos = ma.protoNames()
    return protos.includes('webtransport')
}

function isWebRTCAddr(ma: Multiaddr): boolean {
    const protos = ma.protoNames()
    return protos.includes('webrtc') || protos.includes('webrtc-direct')
}

function selectPreferredBootstrapAddrs(addrs: string[]): Multiaddr[] {
    const seen = new Set<string>()
    const all = addrs.map((a) => multiaddr(a))

    // Rank: WS/WSS > WebTransport > WebRTC > others
    const ws = all.filter(isWebsocketAddr)
    const wt = all.filter(isWebTransportAddr)
    const wrtc = all.filter(isWebRTCAddr)
    const rest = all.filter((a) => !ws.includes(a) && !wt.includes(a) && !wrtc.includes(a))

    const ordered = [...ws, ...wt, ...wrtc, ...rest]
    const result: Multiaddr[] = []
    for (const ma of ordered) {
        const s = ma.toString()
        if (seen.has(s)) continue
        seen.add(s)
        result.push(ma)
        if (result.length >= 6) break // cap initial concurrent dials
    }
    return result
}


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
        console.log('[dyson-sdk] payload is not an object or null ', payload)
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
    private readonly onPubsubMessage: (evt: CustomEvent<any>) => void
    private discoveryInterval?: ReturnType<typeof setInterval>
    private bootstrapRefreshInterval?: ReturnType<typeof setInterval>
    private readonly bootstrapUrl: string


    constructor(libp2p: Libp2p, bootstrap: BootstrapInfo, discoveryTopic: string, gossipLog: IndexedDBGossipLog<DysonLogPayload>, bootstrapUrl: string) {
        this.libp2p = libp2p
        this.bootstrap = bootstrap
        this.chainId = bootstrap.chainId
        this.topicPrefix = bootstrap.topicPrefix.endsWith('/') ? bootstrap.topicPrefix : `${bootstrap.topicPrefix}/`
        this.peerId = libp2p.peerId.toString()
        this.discoveryTopic = discoveryTopic
        this.gossipLog = gossipLog
        this.bootstrapUrl = bootstrapUrl

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

        this.onPubsubMessage = (evt: CustomEvent<any>) => {
            const detail = evt?.detail
            if (!detail?.data || !detail?.topic) {
                console.log('[dyson-sdk] pubsub message missing data or topic', { data: !!detail?.data, topic: !!detail?.topic })
                return
            }

            const topic = detail.topic
            const from = detail.from
            console.log(`[dyson-sdk] pubsub message received: topic=${topic}, from=${from}, dataLen=${detail.data?.length || 0}`)

            // Skip discovery topic messages (they're handled by pubsubPeerDiscovery)
            if (topic === this.discoveryTopic) {
                console.log('[dyson-sdk] skipping validation of discovery topic message')
                return
            }

            const entry = this.topics.get(topic)
            if (!entry) {
                console.log(`[dyson-sdk] no subscription for topic: ${topic}`)
                return
            }
            if (entry.handlers.size === 0) {
                console.log(`[dyson-sdk] no handlers for topic: ${topic}`)
                return
            }

            // Validate ADR-36 envelope like the server; reject frames that fail
            try {
                const { envelope } = validateEnvelope(detail.data, topic, from, {
                    maxEnvelopeBytes: DEFAULT_MAX_ENVELOPE_BYTES,
                })

                // Verify ADR-36 signature locally, then append
                const isFromSelf = from === this.peerId
                void verifyAdr36Envelope(envelope).then(() => {
                    if (!isFromSelf) {
                        const envelopeJson = JSON.stringify(envelope)
                        const logPayload: DysonLogPayload = { topic, data: envelopeJson, from }
                        void this.gossipLog.append(logPayload)
                    } else {
                        console.log(`[dyson-sdk] skipping GossipLog storage for self-message (already stored on publish)`)
                    }
                }).catch((err) => {
                    console.warn('[dyson-sdk] signature verification failed, dropping frame:', err)
                })
                // Don't dispatch here - GossipLog consumer will handle all dispatches
            } catch (err) {
                console.warn('[dyson-sdk] envelope validation failed, dropping frame:', err)
                // Drop invalid frame silently (server would reject at validator)
            }
        }

        libp2p.addEventListener('peer:discovery', this.onPeerDiscovery)
        libp2p.addEventListener('peer:connect', this.onPeerConnect)
        libp2p.addEventListener('peer:disconnect', this.onPeerDisconnect)

        // Listen to pubsub messages and dispatch to handlers
        this.pubsub.addEventListener('message', this.onPubsubMessage)

        this.gossipLog.setConsumer(async (signedMessage) => {
            const payload = signedMessage.message.payload
            if (isDysonLogPayload(payload)) {
                this.dispatchLogPayload(payload)
            }
            return undefined
        })

        this.discoveryInterval = setInterval(() => this.publishPresence('heartbeat'), 30_000)
        // Periodically refresh bootstrap info and (re)connect to ensure relay reservations survive restarts
        this.bootstrapRefreshInterval = setInterval(() => {
            void this.refreshBootstrapInfo()
        }, 60_000)
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
            await this.pubsub.unsubscribe(topic)
            this.topics.delete(topic)
        }
    }

    async publish(params: PublishParams): Promise<void> {
        const { topic, payload, signer, peerId } = params
        console.log(`[dyson-sdk] publish() called: topic=${topic}, payloadLen=${payload.length}`)

        const envelope = await createAdr36Envelope({
            chainId: this.chainId,
            topic,
            payload,
            signer,
            peerId: peerId ?? this.peerId,
        })
        const envelopeJson = JSON.stringify(envelope)
        const payloadBytes = uint8FromString(envelopeJson)

        const peers = this.pubsub.getPeers()
        const topicPeers = this.pubsub.getSubscribers(topic)
        console.log(`[dyson-sdk] publishing to pubsub: topic=${topic}, envelopeLen=${payloadBytes.length}, peers=${peers.length}, topicPeers=${topicPeers.length}`)
        if (peers.length > 0) {
            console.log(`[dyson-sdk] peer IDs:`, peers.map((p: PeerId) => p.toString()))
        }
        if (topicPeers.length > 0) {
            console.log(`[dyson-sdk] topic peer IDs:`, topicPeers.map((p: PeerId) => p.toString()))
        }

        // Publish to pubsub mesh
        await this.pubsub.publish(topic, payloadBytes)
        console.log(`[dyson-sdk] publish() succeeded`)

        // Store in GossipLog for replay
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
            await this.pubsub.unsubscribe(topic)
        }
        this.topics.clear()

        this.libp2p.removeEventListener('peer:discovery', this.onPeerDiscovery)
        this.libp2p.removeEventListener('peer:connect', this.onPeerConnect)
        this.libp2p.removeEventListener('peer:disconnect', this.onPeerDisconnect)

        // Remove pubsub message listener
        this.pubsub.removeEventListener('message', this.onPubsubMessage as any)

        if (this.discoveryInterval) {
            clearInterval(this.discoveryInterval)
            this.discoveryInterval = undefined
        }
        if (this.bootstrapRefreshInterval) {
            clearInterval(this.bootstrapRefreshInterval)
            this.bootstrapRefreshInterval = undefined
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
            // Expected: address book operations may fail, not critical
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
            // Expected: address book may not be available
            console.warn('[dyson-sdk] failed to read peer addrs', err)
        }
        const candidateAddrs = [...discoveredAddrs, ...storedAddrs]

        const preferred = candidateAddrs.filter((addr) => addr.protoNames().includes('webrtc') && addr.protoNames().includes('p2p-circuit'))
        const fallbacks = candidateAddrs.filter((addr) => !preferred.includes(addr))
        const targets = preferred.length > 0 ? preferred : fallbacks

        for (const addr of targets) {
            // Ensure /p2p/<peerId> suffix for transports like webrtc that require a target peer id
            const base = addr.toString()
            const hasPeerSuffix = /\/p2p\/[^/]+$/.test(base)
            const dialAddr = hasPeerSuffix ? addr : multiaddr(`${base}/p2p/${peerId.toString()}`)
            try {
                console.log(`[dyson-sdk] dialing ${dialAddr.toString()} (${reason})`)
                const conn = await this.libp2p.dial(dialAddr)
                console.log(`[dyson-sdk] browser mesh connected ${conn.remotePeer}`)
                this.peerState.set(peerId.toString(), { backoffMs: MIN_BROWSER_BACKOFF_MS })
                const cm = this.getConnectionManager()
                if (cm?.protect) {
                    cm.protect(peerId, BROWSER_PEER_TAG)
                }
                return
            } catch (err) {
                // Expected: some addresses may not be dialable (e.g., circuit relay paths)
                // Try next address
                console.warn(`[dyson-sdk] dial failed for ${dialAddr.toString()}:`, err)
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
            // Expected: all dial attempts failed, schedule redial
            console.warn(`[dyson-sdk] peer dial failed for ${peerId.toString()}:`, err)
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

        // GossipLog is the source of truth - dispatch all messages from here
        console.log(`[dyson-sdk] dispatching message from GossipLog to ${entry.handlers.size} handlers`)
        for (const handler of entry.handlers) {
            handler(message)
        }
    }

    private buildMessageFromPayload(payload: DysonLogPayload): DysonMessage {
        const envelope = JSON.parse(payload.data)
        const bytes = uint8FromString(JSON.stringify(envelope))
        return decodeMessage({
            data: bytes,
            topic: payload.topic,
            from: payload.from ?? this.peerId,
        }, payload.topic)
    }

    private async replayForHandler(topic: string, handler: DysonMessageHandler): Promise<void> {
        for await (const signedMessage of this.gossipLog.iterate()) {
            const payload = signedMessage.message.payload
            if (!isDysonLogPayload(payload) || payload.topic !== topic) {
                continue
            }

            const message = this.buildMessageFromPayload(payload)
            handler(message)
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

        void this.pubsub.publish(this.discoveryTopic, uint8FromString(JSON.stringify(payload)))
    }

    private async refreshBootstrapInfo(): Promise<void> {
        try {
            const res = await fetch(this.bootstrapUrl)
            if (!res?.ok) {
                console.warn('[dyson-sdk] bootstrap refresh failed', res?.status)
                return
            }
            const updated = (await res.json()) as BootstrapInfo
            const changed = JSON.stringify(updated) !== JSON.stringify(this.bootstrap)
            if (changed) {
                console.log('[dyson-sdk] bootstrap info updated')
                    ; (this as any).bootstrap = updated
            }

            // Try to (re)connect to the server addrs to renew relay reservations
            let connected = false
            for (const addr of updated.addrs ?? []) {
                try {
                    const conn = await this.libp2p.dial(multiaddr(addr))
                    await waitForIdentify(this.libp2p, conn.remotePeer, 5000)
                    await waitForRelayReservation(this.libp2p)
                    connected = true
                    break
                } catch (err) {
                    console.warn('[dyson-sdk] refresh dial failed', addr, err)
                }
            }
            if (!connected) {
                // As a fallback, prefer dialing any discovery-learned peers to keep mesh alive
                console.warn('[dyson-sdk] refresh did not connect to bootstrap peers')
            }

            // Announce updated presence periodically
            this.publishPresence('bootstrap-refresh')
        } catch (err) {
            console.warn('[dyson-sdk] bootstrap refresh error', err)
        }
    }
}

export async function createDysonClient(options: CreateDysonClientOptions = {}): Promise<DysonClient> {
    const bootstrapUrl = options.bootstrapUrl ?? '/libp2p/bootstrap'


    const res = await fetch(bootstrapUrl)
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
                discoverRelays: 3,  // Discover at least 3 relays
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
                interval: 2_000,
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

    // Dial bootstrap server(s) concurrently (non-blocking) and try to establish relay reservation in background
    const bootstrapAddrs = bootstrap.addrs ?? []
        ; (async () => {
            if (bootstrapAddrs.length === 0) {
                console.warn('[dyson-sdk] no bootstrap addrs provided')
                return
            }
            try {
                const preferred = selectPreferredBootstrapAddrs(bootstrapAddrs)
                const connectedLogged = new Set<string>()
                const dialPromises = preferred.map(async (ma) => {
                    console.log(`[dyson-sdk] dialing ${ma.toString()}...`)
                    const conn = await node.dial(ma)
                    const pid = conn.remotePeer.toString()
                    const addrStr = conn.remoteAddr?.toString?.() ?? ''
                    if (!connectedLogged.has(pid)) {
                        console.log(`[dyson-sdk] connected to ${pid} via ${addrStr}`)
                        connectedLogged.add(pid)
                    }
                    // Best-effort identify and relay reservation (do not block UI)
                    void waitForIdentify(node, conn.remotePeer, isWebRTCAddr(ma) ? 8000 : 3000)
                    void waitForRelayReservation(node, 2500)
                    return conn
                })
                await promiseAny(dialPromises)
            } catch (err) {
                // Expected: some bootstrap peers may be unavailable
                console.warn('[dyson-sdk] bootstrap concurrent dial failed', err)
            }
        })()

    // Log addresses
    const myAddrs = node.getMultiaddrs()
    const relayAddrs = myAddrs.filter(ma =>
        ma.protoNames().includes('p2p-circuit') && ma.protoNames().includes('webrtc')
    )
    console.log('[dyson-sdk] my relay addresses:', relayAddrs.map(a => a.toString()))

    return new DysonClientImpl(node, bootstrap, discoveryTopic, gossipLog, bootstrapUrl)
}

async function waitForIdentify(node: Libp2p, peerId: PeerId, timeoutMs = 1000): Promise<void> {
    const key = peerId.toString()
    const existing = identifyInFlight.get(key)
    if (existing) return existing

    const p = new Promise<void>((resolve) => {
        const signal = createTimeoutSignal(timeoutMs)
        const onIdentify = (evt: any) => {
            if (evt?.detail?.peerId?.toString() === key) {
                node.removeEventListener('peer:identify', onIdentify)
                signal?.removeEventListener?.('abort', onAbort as any)
                resolve()
                identifyInFlight.delete(key)
            }
        }
        const onAbort = () => {
            node.removeEventListener('peer:identify', onIdentify)
            identifyInFlight.delete(key)
            resolve()
        }
        node.addEventListener('peer:identify', onIdentify)
        if (signal) signal.addEventListener('abort', onAbort, { once: true })
    })
    identifyInFlight.set(key, p)
    return p
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
            console.log('[dyson-sdk] cleanup called')
            if (settled) return
            settled = true
            node.removeEventListener('self:peer:update', onSelfPeerUpdate)
            signal?.removeEventListener('abort', onAbort)
            resolve()
            console.log('[dyson-sdk] cleanup resolved')
        }
        const onSelfPeerUpdate = () => {
            console.log('[dyson-sdk] self:peer:update', hasReservation())
            if (hasReservation()) {
                console.log('[dyson-sdk] relay reservation created')
                cleanup()
            }
        }
        const onAbort = () => {
            console.info('[dyson-sdk] relay reservation wait timed out')
            cleanup()
        }

        node.addEventListener('self:peer:update', onSelfPeerUpdate)
        if (signal) {
            console.log('[dyson-sdk] adding abort listener to signal', signal)
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

    let envelope: MsgArbitraryData | null = null
    let payload = new Uint8Array()
    let payloadJson: unknown

    try {
        envelope = JSON.parse(uint8ToString(raw)) as MsgArbitraryData
        const msg = envelope?.body?.messages?.[0]
        const dataStr = msg?.data
        if (typeof dataStr === 'string' && dataStr.length > 0) {
            // Data is raw UTF-8 text
            payload = new TextEncoder().encode(dataStr)
            // Try to parse as JSON for payloadJson (optional)
            try {
                payloadJson = JSON.parse(dataStr)
            } catch {
                // Not JSON, payloadJson remains undefined
            }
        }
    } catch (err) {
        // Expected: malformed messages may fail to decode, return what we have
        console.warn('[dyson-sdk] decode error:', err)
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


interface ValidationLimits {
    maxEnvelopeBytes: number
}

function validateEnvelope(rawInput: Uint8Array, topic: string, fromPeerId: string, limits: ValidationLimits): { envelope: MsgArbitraryData } {
    const raw: Uint8Array = rawInput instanceof Uint8Array ? rawInput : new Uint8Array(rawInput ?? [])
    if (raw.length > limits.maxEnvelopeBytes) {
        throw new Error(`envelope too large: ${raw.length} bytes`)
    }

    let envelope: MsgArbitraryData
    try {
        envelope = JSON.parse(uint8ToString(raw)) as MsgArbitraryData
    } catch (err) {
        throw new Error('invalid payload json')
    }

    if (!envelope || typeof envelope !== 'object') {
        throw new Error('invalid envelope type')
    }
    if (!envelope.body || !envelope.auth_info || !Array.isArray(envelope.signatures) || envelope.signatures.length === 0) {
        throw new Error('missing required fields: body, auth_info, or signatures')
    }

    const messages = (envelope.body as any)?.messages
    if (!Array.isArray(messages) || messages.length !== 1) {
        throw new Error('tx must contain exactly one message')
    }
    const msg = messages[0] as any
    if (msg['@type'] !== '/dysonprotocol.script.v1.MsgArbitraryData') {
        throw new Error(`unexpected message type: ${msg['@type']}`)
    }
    // app_domain is no longer compared to the topic here
    if (typeof msg.data !== 'string' || msg.data.length === 0) {
        throw new Error('missing data field')
    }
    // Validate metadata.peerId
    if (typeof msg.metadata !== 'string' || msg.metadata.length === 0) {
        throw new Error('missing metadata field')
    }
    let metadataObj: any
    try {
        metadataObj = JSON.parse(msg.metadata)
    } catch {
        throw new Error('invalid metadata json')
    }
    const peerId = String(metadataObj?.peerId ?? '').trim()
    if (!peerId) {
        throw new Error('missing peerId in metadata')
    }
    if (fromPeerId && peerId !== String(fromPeerId).trim()) {
        throw new Error(`peerId mismatch: payload=${peerId} sender=${fromPeerId}`)
    }

    return { envelope }
}


