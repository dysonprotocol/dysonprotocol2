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
import { multiaddr, Multiaddr } from '@multiformats/multiaddr'
import { fromString as uint8FromString } from 'uint8arrays/from-string'
import { toString as uint8ToString } from 'uint8arrays/to-string'
import { fromBase64 } from '@cosmjs/encoding'
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
    listener: (evt: CustomEvent<any>) => void
    handlers: Set<DysonMessageHandler>
}

const MIN_BROWSER_BACKOFF_MS = 5_000
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

    private readonly pubsub: any
    private readonly topics = new Map<string, TopicRegistryEntry>()
    private readonly peerState = new Map<string, PeerConnectionState>()
    private readonly onPeerDiscovery: (evt: CustomEvent<any>) => void
    private readonly onPeerConnect: (evt: CustomEvent<any>) => void
    private readonly onPeerDisconnect: (evt: CustomEvent<any>) => void
    private discoveryInterval?: ReturnType<typeof setInterval>

    constructor(libp2p: Libp2p, bootstrap: BootstrapInfo, discoveryTopic: string) {
        this.libp2p = libp2p
        this.bootstrap = bootstrap
        this.chainId = bootstrap.rendezvous
        this.topicPrefix = bootstrap.topicPrefix.endsWith('/') ? bootstrap.topicPrefix : `${bootstrap.topicPrefix}/`
        this.peerId = libp2p.peerId.toString()
        this.discoveryTopic = discoveryTopic
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

            const cm = this.libp2p.connectionManager
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
                listener: (evt: CustomEvent<any>) => {
                    const detail = evt.detail
                    if (!detail || detail.topic !== normalisedTopic) return
                    const message = decodeMessage(detail, normalisedTopic)
                    for (const fn of entry!.handlers) {
                        try {
                            fn(message)
                        } catch (err) {
                            console.error('Dyson handler error', err)
                        }
                    }
                },
            }
            this.pubsub.addEventListener('message', entry.listener)
            this.topics.set(normalisedTopic, entry)
        }
        entry.handlers.add(handler)
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
            this.pubsub.removeEventListener('message', entry.listener)
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
        await this.pubsub.publish(topic, uint8FromString(JSON.stringify(envelope)))
    }

    async publishJson(params: PublishJsonParams): Promise<void> {
        const { root, suffix, data, signer, peerId } = params
        const topic = this.buildTopic(root, suffix)
        const payloadBytes = uint8FromString(JSON.stringify(data))
        await this.publish({ topic, payload: payloadBytes, signer, peerId })
    }

    async stop(): Promise<void> {
        for (const [topic, entry] of this.topics.entries()) {
            this.pubsub.removeEventListener('message', entry.listener)
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
    }

    private storeKnownAddrs(peerId: PeerId, addrs: Multiaddr[]): void {
        if (!addrs || addrs.length === 0) {
            return
        }

        const addressBook = this.libp2p.peerStore?.addressBook
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
            storedAddrs = (this.libp2p.peerStore?.addressBook?.get?.(peerId) ?? []) as Multiaddr[]
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
                const cm = this.libp2p.connectionManager
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
            const cm = this.libp2p.connectionManager
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

        const jitter = Math.max(state.backoffMs * 0.5, 1_000)
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

    console.log(`[dyson-sdk] chainID: ${bootstrap.rendezvous}`)
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
            })
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
            await waitForRelayReservation(node, 5000)

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

    return new DysonClientImpl(node, bootstrap, discoveryTopic)
}

async function waitForIdentify(node: Libp2p, peerId: PeerId): Promise<void> {
    return new Promise((resolve) => {
        const onIdentify = (evt: any) => {
            if (evt?.detail?.peerId?.toString() === peerId.toString()) {
                console.log(`[dyson-sdk] identified peer ${peerId}`)
                node.removeEventListener('peer:identify', onIdentify)
                resolve()
            }
        }
        node.addEventListener('peer:identify', onIdentify)
        setTimeout(() => {
            node.removeEventListener('peer:identify', onIdentify)
            resolve()
        }, 3000)
    })
}

async function waitForRelayReservation(node: Libp2p, timeoutMs: number): Promise<void> {
    return new Promise((resolve) => {
        const checkReservation = () => {
            const addrs = node.getMultiaddrs()
            const hasRelay = addrs.some(ma => ma.protoNames().includes('p2p-circuit'))
            if (hasRelay) {
                console.log('[dyson-sdk] relay reservation created')
                resolve()
            }
        }

        const onSelfPeerUpdate = () => checkReservation()
        node.addEventListener('self:peer:update', onSelfPeerUpdate)

        checkReservation()

        setTimeout(() => {
            node.removeEventListener('self:peer:update', onSelfPeerUpdate)
            console.warn('[dyson-sdk] relay reservation timeout')
            resolve()
        }, timeoutMs)
    })
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
        if (typeof dataStr === 'string') {
            const dataObj = JSON.parse(dataStr)
            if (dataObj?.payload_b64) {
                payload = fromBase64(dataObj.payload_b64)
                const maybeJson = textDecoder.decode(payload)
                try {
                    payloadJson = JSON.parse(maybeJson)
                } catch {
                    // not json, ignore
                }
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

