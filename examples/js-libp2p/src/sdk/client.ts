import { createLibp2p, Libp2p } from 'libp2p'
import { gossipsub } from '@chainsafe/libp2p-gossipsub'
import { noise } from '@chainsafe/libp2p-noise'
import { yamux } from '@chainsafe/libp2p-yamux'
import { identify } from '@libp2p/identify'
import { circuitRelayServer, circuitRelayTransport } from '@libp2p/circuit-relay-v2'
import { webSockets } from '@libp2p/websockets'
import { webTransport } from '@libp2p/webtransport'
import { webRTC, webRTCDirect } from '@libp2p/webrtc'
import { pubsubPeerDiscovery } from '@libp2p/pubsub-peer-discovery'
import { multiaddr } from '@multiformats/multiaddr'
import { fromString as uint8FromString } from 'uint8arrays/from-string'
import { toString as uint8ToString } from 'uint8arrays/to-string'
import { fromBase64 } from '@cosmjs/encoding'

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

class DysonClientImpl implements DysonClient {
    readonly libp2p: Libp2p
    readonly bootstrap: BootstrapInfo
    readonly chainId: string
    readonly topicPrefix: string
    readonly peerId: string

    private readonly pubsub: any
    private readonly topics = new Map<string, TopicRegistryEntry>()

    constructor(libp2p: Libp2p, bootstrap: BootstrapInfo) {
        this.libp2p = libp2p
        this.bootstrap = bootstrap
        this.chainId = bootstrap.rendezvous
        this.topicPrefix = bootstrap.topicPrefix.endsWith('/') ? bootstrap.topicPrefix : `${bootstrap.topicPrefix}/`
        this.peerId = libp2p.peerId.toString()
        this.pubsub = libp2p.services.pubsub

        libp2p.addEventListener('peer:discovery', async (evt: any) => {
            const info = evt?.detail
            if (!info?.id) return
            try {
                await this.libp2p.dial(info.id)
            } catch (err) {
                console.warn('Dyson discovery dial failed', err)
            }
        })
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
        await this.libp2p.stop()
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

    const node = await createLibp2p({
        addresses: {
            listen: ['/webrtc'],
        },
        transports: [webTransport(), webSockets(), webRTC(), webRTCDirect(), circuitRelayTransport()],
        connectionEncrypters: [noise()],
        streamMuxers: [yamux()],
        connectionGater: {
            denyDialMultiaddr: async () => false,
        },
        peerDiscovery: [
            pubsubPeerDiscovery({
                interval: 10_000,
                topics: [discoveryTopic],
                listenOnly: false,
            }),
        ],
        services: {
            identify: identify(),
            relay: circuitRelayServer(),
            pubsub: gossipsub({ emitSelf: true, allowPublishToZeroTopicPeers: true }),
        },
    })

    console.log(`[dyson-sdk] created libp2p peerId=${node.peerId.toString()}`)

    // Start the node to begin protocol negotiations
    await node.start()
    console.log(`[dyson-sdk] node started`)

    // Subscribe to discovery topic BEFORE dialing so GossipSub announces it in first heartbeat
    node.services.pubsub.subscribe(discoveryTopic)
    console.log(`[dyson-sdk] pre-subscribed to discovery topic: ${discoveryTopic}`)
    console.log(`[dyson-sdk] pubsub getPeers():`, node.services.pubsub.getPeers())
    console.log(`[dyson-sdk] libp2p connections:`, node.getConnections().map((c: any) => c.remotePeer.toString()))

    // Dial and wait for identify to complete so pubsub knows about the peer
    let connected = false
    for (const addr of bootstrap.addrs ?? []) {
        if (connected) break
        try {
            console.log(`[dyson-sdk] dialing ${addr}...`)
            const conn = await node.dial(multiaddr(addr))
            console.log(`[dyson-sdk] connected to ${conn.remotePeer} via ${conn.remoteAddr}`)

            // Wait for identify to complete (gives pubsub time to discover peer protocols)
            await new Promise((resolve) => {
                const onIdentify = (evt: any) => {
                    if (evt?.detail?.peerId?.toString() === conn.remotePeer.toString()) {
                        console.log(`[dyson-sdk] identified peer ${conn.remotePeer}`)
                        node.removeEventListener('peer:identify', onIdentify)
                        resolve(undefined)
                    }
                }
                node.addEventListener('peer:identify', onIdentify)
                setTimeout(() => {
                    node.removeEventListener('peer:identify', onIdentify)
                    resolve(undefined)
                }, 3000)
            })

            // Wait for GossipSub heartbeat to fire (default 1s interval)
            console.log(`[dyson-sdk] waiting for gossipsub heartbeat...`)

            console.log(`[dyson-sdk] pubsub peers after heartbeat:`, node.services.pubsub.getPeers())

            connected = true
        } catch (err) {
            console.warn('[dyson-sdk] dial failed', addr, err)
        }
    }

    if (!connected) {
        console.warn('[dyson-sdk] no successful connections to bootstrap peers')
    }

    return new DysonClientImpl(node, bootstrap)
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

