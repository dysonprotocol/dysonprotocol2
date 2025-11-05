<template>
  <div>
    <h1>Dyson JS libp2p Demo</h1>
    <p>
      Demo connecting to Dyson peer via libp2p, using GossipSub for messaging, ADR-36 signing, and subscription management.
    </p>

    <!-- Connection Status -->
    <section>
      <h2>Connection Status</h2>
      <div>
        <button @click="handleConnect" :disabled="connecting">
          {{ connected ? 'Disconnect' : 'Connect' }}
        </button> | 
        <span>{{ connectionStatus }}</span>
        <div v-if="connected">Peer ID: {{ peerId }}</div>
      </div>
      <div v-if="connected">
        <details>
          <summary>Bootstrap Info</summary>
          <pre>{{ JSON.stringify(bootstrap, null, 2) }}</pre>
        </details>
      </div>
    </section>

    <!-- Peer Connections -->
    <section v-if="connected">
      <h2>Peer Connections</h2>
      <div>
        <span>Connected: <strong>{{ connectedPeers.length }}</strong></span> |
        <span>Total Known: <strong>{{ allPeers.length }}</strong></span> |
        <span>Mesh Peers: <strong>{{ meshPeersCount }}</strong></span>
      </div>
      <ul>
        <li v-for="p in allPeers" :key="p.id">
          <div>
            <code>{{ p.id }}</code> |
            <small>
              {{ connectedById[p.id] ? 'connected' : 'discovered' }}
              <template v-if="connectedById[p.id]"> · {{ connectedById[p.id].direction || '—' }} · {{ connectedById[p.id].status || '—' }}</template>
            </small>
          </div>
          <div><code>{{ connectedById[p.id]?.remoteAddr || (p.addrs[0] || '—') }}</code></div>
        </li>
      </ul>
    </section>

    <!-- GossipSub Mesh State -->
    <section v-if="connected">
      <h2>GossipSub Mesh State</h2>
      <div>
        <div>Total Pubsub Peers: <strong>{{ pubsubPeersCount }}</strong></div>
        <div>Active Topics: <strong>{{ subscriptions.length }}</strong></div>
      </div>
      <div v-if="meshDetails.length > 0">
        <div v-for="detail in meshDetails" :key="detail.topic">
          <strong>{{ detail.topic }}</strong>
          <span>Mesh: {{ detail.meshCount }}</span>
          <span>Subscribers: {{ detail.subscribersCount }}</span>
        </div>
      </div>
    </section>

    <!-- Wallet Management -->
    <section>
      <h2>Wallet</h2>
      <div>
        <label>
          Mnemonic seed (12 or 24 words)
          <textarea v-model="mnemonic" rows="3"></textarea>
        </label>
        <div>
          <button @click="generateMnemonic">Generate Seed</button>
          <button @click="useMnemonic">Use Seed</button>
        </div>
        <div>
          <p>CosmJS address: <code>{{ cosmjsAddress || '—' }}</code></p>
          <p>Keplr address: <code>{{ keplrAddress || (keplrAvailable ? '—' : 'Keplr not detected') }}</code></p>
        </div>
      </div>
    </section>

    <!-- Subscriptions -->
    <section v-if="connected">
      <h2>Subscriptions</h2>
      <div>
        <div v-if="subscriptions.length === 0">No active subscriptions</div>
        <div v-for="sub in subscriptions" :key="sub.topic">
          <div>
            <code>{{ sub.topic }}</code>
            <button @click="unsubscribe(sub.topic)">Unsubscribe</button>
          </div>
          <div>Handlers: {{ sub.handlers }}, Messages: {{ sub.messageCount }}</div>

          <!-- Per-topic message log (GossipLog-backed, RX only) -->
          <ul>
            <li v-for="msg in (topicMessages[sub.topic] || [])" :key="msg.id">
              <details>
                <summary>
                  {{ msg.payload }}
                </summary>
                <pre>{{ msg.raw }}</pre>
              </details>
            </li>
          </ul>
        </div>
        <div>
          <label>
            Subscribe to topic:
            <input v-model="newTopic" type="text" placeholder="/chainId/v1/address/suffix" />
          </label>
          <button @click="subscribeToTopic" :disabled="!newTopic.trim()">Subscribe</button>
        </div>
      </div>
    </section>

    <!-- Publish Message -->
    <section>
      <h2>Publish Message</h2>
      <div>
        <label>
          Topic suffix (appended to <code>/CHAIN_ID/v1/&lt;address&gt;/</code>)
          <input v-model="topicSuffix" type="text" />
        </label>
        <label>
          Message payload (JSON or any text)
          <textarea v-model="payload" rows="4"></textarea>
        </label>
        <div>
          <button @click="publishWithCosmjs" :disabled="!canPublishCosmjs" :title="publishCosmjsTitle">
            Sign & Publish (CosmJS)
          </button>
          <button @click="publishWithKeplr" :disabled="!canPublishKeplr" :title="publishKeplrTitle">
            Sign & Publish (Keplr)
          </button>
        </div>
        <div v-if="publishing">
          <span v-if="signingStatus">Signing...</span>
          <span v-if="publishingStatus">Publishing...</span>
        </div>
      </div>
    </section>

    <!-- ADR36 Signing Info -->
    <section v-if="lastSignature">
      <h2>Last ADR36 Signature</h2>
      <div>
        <div><strong>Signer:</strong> {{ lastSignature.signer }}</div>
        <div><strong>Method:</strong> {{ lastSignature.method }}</div>
        <div><strong>Status:</strong> <span>Valid</span></div>
        <details>
          <summary>Envelope JSON</summary>
          <pre>{{ lastSignature.envelope }}</pre>
        </details>
      </div>
    </section>

    <!-- Messages -->
    <section>
      <h2>Messages</h2>
      <div>
        <button @click="clearMessages">Clear</button>
        <input v-model="messageFilter" type="text" placeholder="Filter by topic or signer..." />
        <select v-model="messageFilterType">
          <option value="all">All</option>
          <option value="sent">Sent</option>
          <option value="received">Received</option>
        </select>
      </div>
      <ul>
        <li v-for="msg in filteredMessages" :key="msg.id">
          <details>
            <summary>
              <strong>{{ msg.type === 'sent' ? 'Sent' : 'Received' }}</strong>
              · {{ formatTime(msg.timestamp) }} · <code>{{ msg.topic }}</code>
              · signer {{ msg.signer }} · {{ msg.size }} bytes
            </summary>
            <pre>{{ msg.raw || msg.payload }}</pre>
          </details>
        </li>
      </ul>
    </section>

    <!-- Statistics -->
    <section v-if="connected">
      <h2>Statistics</h2>
      <div>
        <div>
          <div>Messages Sent</div>
          <div>{{ stats.messagesSent }}</div>
        </div>
        <div>
          <div>Messages Received</div>
          <div>{{ stats.messagesReceived }}</div>
        </div>
        <div>
          <div>Bytes Sent</div>
          <div>{{ formatBytes(stats.bytesSent) }}</div>
        </div>
        <div>
          <div>Bytes Received</div>
          <div>{{ formatBytes(stats.bytesReceived) }}</div>
        </div>
        <div>
          <div>Uptime</div>
          <div>{{ formatUptime(stats.uptime) }}</div>
        </div>
      </div>
    </section>

    <!-- Debug Log -->
    <section>
      <h2>Debug Log</h2>
      <div>
        <button @click="clearLog">Clear Log</button>
        <button @click="exportLog">Export Log</button>
      </div>
      <pre ref="logRef">{{ logOutput }}</pre>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { DirectSecp256k1HdWallet } from '@cosmjs/proto-signing'
import { fromString as uint8FromString } from 'uint8arrays/from-string'
import { toString as uint8ToString } from 'uint8arrays/to-string'

import {
  createDysonClient,
  createKeplrSigner,
  createOfflineSignerSigner,
  DysonClient,
  DysonMessage,
} from '@dyson/libp2p'

const DEFAULT_PREFIX = 'dys2'

// Connection state
const connecting = ref(false)
const connected = ref(false)
const client = ref<DysonClient | undefined>()
const peerId = ref('')
const bootstrap = ref<any>(null)
const connectionStartTime = ref<number>(0)

// Peer state
const connectedPeers = ref<Array<{ id: string; addrs: string[]; protocols: string[]; connCount: number; direction: string; status: string; remoteAddr: string; streams: number; openedMs: number }>>([])
const allPeers = ref<Array<{ id: string; addrs: string[] }>>([])
const pubsubPeersCount = ref(0)
const meshPeersCount = ref(0)

// Wallet state
const mnemonic = ref('wise quiz boat phone alone govern crash estate face faith alcohol same')
const cosmjsWallet = ref<DirectSecp256k1HdWallet | undefined>()
const cosmjsAddress = ref('')
const keplrAvailable = ref(typeof window.keplr !== 'undefined')
const keplrAddress = ref('')

// Publishing state
const topicSuffix = ref('demo')
const payload = ref('{"text":"Hello Dyson"}')
const publishing = ref(false)
const signingStatus = ref(false)
const publishingStatus = ref(false)
const lastSignature = ref<{ signer: string; method: string; envelope: string } | null>(null)

// Subscriptions
const subscriptions = ref<Array<{ topic: string; handlers: number; messageCount: number }>>([])
const subscribedTopics = new Map<string, { handler: (msg: DysonMessage) => void; messageCount: number }>()
const newTopic = ref('')

// Per-topic UI state
const topicDrafts = ref<Record<string, string>>({})
const topicMessages = ref<Record<string, MessageItem[]>>({})

// Messages
interface MessageItem {
  id: string
  type: 'sent' | 'received'
  topic: string
  signer: string
  from: string
  payload: string
  raw?: string
  timestamp: number
  size: number
}
const messages = ref<MessageItem[]>([])
const messageFilter = ref('')
const messageFilterType = ref<'all' | 'sent' | 'received'>('all')

// Statistics
const stats = ref({
  messagesSent: 0,
  messagesReceived: 0,
  bytesSent: 0,
  bytesReceived: 0,
  uptime: 0,
})

// Logging
const logOutput = ref('')
const logRef = ref<HTMLElement>()

// Update intervals
let updateInterval: ReturnType<typeof setInterval> | null = null

// Computed
const connectionStatus = computed(() => {
  if (connecting.value) return 'Connecting...'
  if (connected.value) return 'Connected'
  return 'Disconnected'
})


const canPublishCosmjs = computed(() => connected.value && !!cosmjsWallet.value && !!cosmjsAddress.value)
const canPublishKeplr = computed(() => connected.value && keplrAvailable.value)

const publishCosmjsTitle = computed(() => {
  if (!cosmjsWallet.value) return 'Generate or paste a mnemonic first'
  if (!connected.value) return 'Connect before publishing'
  return ''
})

const publishKeplrTitle = computed(() => {
  if (!keplrAvailable.value) return 'Keplr extension not detected'
  if (!connected.value) return 'Connect before publishing'
  return ''
})

const filteredMessages = computed(() => {
  let filtered = messages.value
  if (messageFilterType.value !== 'all') {
    filtered = filtered.filter(m => m.type === messageFilterType.value)
  }
  if (messageFilter.value.trim()) {
    const filter = messageFilter.value.toLowerCase()
    filtered = filtered.filter(m => 
      m.topic.toLowerCase().includes(filter) || 
      m.signer.toLowerCase().includes(filter) ||
      m.from.toLowerCase().includes(filter)
    )
  }
  return filtered
})

const meshDetails = computed(() => {
  return subscriptions.value.map(sub => {
    if (!client.value) return { topic: sub.topic, meshCount: 0, subscribersCount: 0 }
    const pubsub = (client.value.libp2p.services as any).pubsub
    if (!pubsub) return { topic: sub.topic, meshCount: 0, subscribersCount: 0 }
    const subscribers = pubsub.getSubscribers(sub.topic) || []
    // Try to get mesh peers if available (GossipSub specific)
    const mesh = (pubsub.getMeshPeers && typeof pubsub.getMeshPeers === 'function' && pubsub.getMeshPeers(sub.topic)) || []
    return {
      topic: sub.topic,
      meshCount: mesh.length,
      subscribersCount: subscribers.length,
    }
  })
})

const connectedById = computed<Record<string, any>>(() => {
  const obj: Record<string, any> = {}
  for (const p of connectedPeers.value) obj[p.id] = p
  return obj
})

// Logging
function log(message: string, data?: any) {
  const ts = new Date().toISOString()
  const line = data !== undefined ? `${ts} [LOG] ${message} ${JSON.stringify(data)}` : `${ts} [LOG] ${message}`
  console.log('[dyson-demo]', message, data ?? '')
  logOutput.value = `${line}\n${logOutput.value || ''}`.slice(0, 100000)
  if (logRef.value) {
    logRef.value.scrollTop = 0
  }
}

function logError(message: string, error: any) {
  const ts = new Date().toISOString()
  const errMsg = error instanceof Error ? error.message : String(error)
  const line = `${ts} [ERROR] ${message}: ${errMsg}`
  console.error('[dyson-demo]', message, error)
  logOutput.value = `${line}\n${logOutput.value || ''}`.slice(0, 100000)
}

// Update peers
function updatePeers() {
  if (!client.value) return
  
  const pubsub = (client.value.libp2p.services as any).pubsub
  if (pubsub) {
    const peers = pubsub.getPeers() || []
    pubsubPeersCount.value = peers.length
    
    const meshPeers = new Set<string>()
    subscriptions.value.forEach(sub => {
      const mesh = pubsub.getMeshPeers?.(sub.topic) || []
      mesh.forEach((p: any) => meshPeers.add(p.toString()))
    })
    meshPeersCount.value = meshPeers.size
  }

  const libp2p: any = client.value.libp2p as any
  const peerStore = libp2p?.peerStore
  const addressBook = peerStore?.addressBook

  // Build connection summaries by remotePeer
  const connections: any[] = libp2p.getConnections?.() || []
  const byPeer = new Map<string, any[]>()
  for (const c of connections) {
    const id = c?.remotePeer?.toString?.() || ''
    if (!id) continue
    const list = byPeer.get(id) || []
    list.push(c)
    byPeer.set(id, list)
  }

  const connected: Array<{ id: string; addrs: string[]; protocols: string[]; connCount: number; direction: string; status: string; remoteAddr: string; streams: number; openedMs: number }> = []
  for (const [id, conns] of byPeer.entries()) {
    const primary: any = conns[0]
    const status: string = String(primary?.status ?? '')
    const direction: string = String(primary?.direction ?? '')
    const remoteAddr: string = primary?.remoteAddr?.toString?.() ?? ''
    const streams: number = Array.isArray(primary?.streams) ? primary.streams.length : 0
    const opened: number = Number(primary?.timeline?.open ?? 0)
    const openedMs: number = opened ? Math.max(0, Date.now() - opened) : 0

    // Protocols best-effort
    let protocols: string[] = []

      const protoBook = peerStore?.protoBook
      if (protoBook?.get) {
        const p = protoBook.get(primary?.remotePeer)
        if (Array.isArray(p)) protocols = p
      }


    // Addresses best-effort: from addressBook or remoteAddr
    let addrs: string[] = []
    
      const abAddrs = addressBook?.get?.(primary?.remotePeer) || []
      addrs = Array.isArray(abAddrs) ? abAddrs.map((a: any) => a.toString?.() || a.multiaddr?.toString?.() || String(a)) : []

    if (addrs.length === 0 && remoteAddr) addrs = [remoteAddr]

    connected.push({
      id,
      addrs,
      protocols,
      connCount: conns.length,
      direction,
      status,
      remoteAddr,
      streams,
      openedMs,
    })
  }
  connectedPeers.value = connected

  // Derive total known peers from pubsub peers and connection peers
  const knownIds = new Set<string>()
  try {
    const psPeers: any[] = (client.value.libp2p.services as any)?.pubsub?.getPeers?.() || []
    for (const p of psPeers) knownIds.add(p?.toString?.() || String(p))
  } catch {}
  for (const id of byPeer.keys()) knownIds.add(id)

  const all: Array<{ id: string; addrs: string[] }> = []
  for (const id of knownIds) {
    let addrs: string[] = []
    try {
      // use addressBook if available by matching any connection's remotePeer
      const conn = byPeer.get(id)?.[0]
      const abAddrs = addressBook?.get?.(conn?.remotePeer) || []
      addrs = Array.isArray(abAddrs) ? abAddrs.map((a: any) => a.toString?.() || a.multiaddr?.toString?.() || String(a)) : []
    } catch {}
    all.push({ id, addrs })
  }
  allPeers.value = all
}

// Update subscriptions list
function updateSubscriptions() {
  if (!client.value) return
  
  subscriptions.value = Array.from(subscribedTopics.entries()).map(([topic, info]) => ({
    topic,
    handlers: 1,
    messageCount: info.messageCount,
  }))
}

// Connection
async function handleConnect() {
  if (connected.value) {
    await disconnect()
    return
  }
  
  connecting.value = true
  log('Connecting to Dyson...')
  
  client.value = await createDysonClient()
  peerId.value = client.value.peerId
  bootstrap.value = client.value.bootstrap
  connectionStartTime.value = Date.now()
  
  log('Connected', { peerId: client.value.peerId, chainId: client.value.chainId })
  log('Bootstrap info', client.value.bootstrap)
  
  connected.value = true
  connecting.value = false
  
  setupEventListeners()
  updatePeers()
  
  // Auto-subscribe if we have an address
  if (cosmjsAddress.value) {
    const topic = buildTopic(cosmjsAddress.value)
    await ensureSubscription(topic)
  }
  
  // Start update interval
  updateInterval = setInterval(() => {
    updatePeers()
    updateSubscriptions()
    if (connected.value) {
      stats.value.uptime = Date.now() - connectionStartTime.value
    }
  }, 2000)
}

async function disconnect() {
  if (client.value) {
    log('Disconnecting...')
    await client.value.stop()
    client.value = undefined
  }
  connected.value = false
  connecting.value = false
  peerId.value = ''
  bootstrap.value = null
  connectedPeers.value = []
  allPeers.value = []
  subscriptions.value = []
  subscribedTopics.clear()
  if (updateInterval) {
    clearInterval(updateInterval)
    updateInterval = null
  }
  log('Disconnected')
}

function setupEventListeners() {
  if (!client.value) return
  
  client.value.libp2p.addEventListener('peer:connect', (e: any) => {
    const peerId = e?.detail?.remotePeer?.toString?.()
    log('peer:connect', { id: peerId })
    updatePeers()
  })
  
  client.value.libp2p.addEventListener('peer:disconnect', (e: any) => {
    const peerId = e?.detail?.remotePeer?.toString?.()
    log('peer:disconnect', { id: peerId })
    updatePeers()
  })
  
  client.value.libp2p.addEventListener('connection:open', (e: any) => {
    const peerId = e?.detail?.remotePeer?.toString?.()
    log('connection:open', { id: peerId })
    updatePeers()
  })
  
  client.value.libp2p.addEventListener('connection:close', (e: any) => {
    const peerId = e?.detail?.remotePeer?.toString?.()
    log('connection:close', { id: peerId })
    updatePeers()
  })
  
  client.value.libp2p.addEventListener('peer:discovery', (e: any) => {
    const info = e?.detail
    log('peer:discovery', { 
      id: info?.id?.toString?.(), 
      addrs: info?.multiaddrs?.map?.((m: any) => m?.toString?.()) 
    })
    updatePeers()
  })
  
  const pubsub = (client.value!.libp2p.services as any).pubsub
  if (pubsub?.addEventListener) {
    pubsub.addEventListener('message', (evt: any) => {
      const d = evt?.detail
      log('pubsub:message', { topic: d?.topic, from: d?.from })
    })
  }
}

// Wallet
async function generateMnemonic() {
  log('Generating mnemonic...')
  const wallet = await DirectSecp256k1HdWallet.generate(12, { prefix: DEFAULT_PREFIX })
  mnemonic.value = wallet.mnemonic
  cosmjsWallet.value = wallet
  const [account] = await wallet.getAccounts()
  cosmjsAddress.value = account.address
  log('Generated mnemonic', { address: cosmjsAddress.value })
  
  if (connected.value && cosmjsAddress.value) {
    const topic = buildTopic(cosmjsAddress.value)
    await ensureSubscription(topic)
  }
}

async function useMnemonic() {
  log('Using mnemonic...')
  const trimmed = mnemonic.value.trim()
  if (!trimmed) {
    cosmjsWallet.value = undefined
    cosmjsAddress.value = ''
    return
  }
  
  cosmjsWallet.value = await DirectSecp256k1HdWallet.fromMnemonic(trimmed, { prefix: DEFAULT_PREFIX })
  const [account] = await cosmjsWallet.value.getAccounts()
  cosmjsAddress.value = account.address
  log('Loaded mnemonic', { address: cosmjsAddress.value })
  
  if (connected.value && cosmjsAddress.value) {
    const topic = buildTopic(cosmjsAddress.value)
    await ensureSubscription(topic)
  }
}

// Subscriptions
function buildTopic(address: string): string {
  if (!client.value) throw new Error('Not connected')
  const suffix = topicSuffix.value.trim() || 'demo'
  return client.value.buildTopic(address, suffix)
}

async function ensureSubscription(topic: string) {
  if (!client.value) return
  if (subscribedTopics.has(topic)) return
  
  log('Subscribing to topic', { topic })
  
  // Initialize per-topic UI state
  if (topicDrafts.value[topic] === undefined) topicDrafts.value[topic] = ''
  if (!topicMessages.value[topic]) topicMessages.value[topic] = []
  
  const messageCount = 0
  const handler = (msg: DysonMessage) => {
    const info = subscribedTopics.get(topic)
    if (info) info.messageCount++
    
    const payloadText = msg.payloadJson !== undefined 
      ? JSON.stringify(msg.payloadJson) 
      : uint8ToString(msg.payload)
    
    // Extract signer address from envelope
    let signerAddress = msg.from
    if (msg.envelope) {
      signerAddress = msg.envelope.body?.messages?.[0]?.signer || msg.from
    }
    
    log('Received message', { topic: msg.topic, from: msg.from, signer: signerAddress, payload: payloadText })
    
    const rawText = msg.envelope ? JSON.stringify(msg.envelope, null, 2) : uint8ToString(msg.raw)
    
    addMessage({
      type: 'received',
      topic: msg.topic,
      signer: signerAddress,
      from: msg.from,
      payload: payloadText,
      raw: rawText,
      size: msg.payload.length,
    })
    
    addTopicMessage({
      type: 'received',
      topic: msg.topic,
      signer: signerAddress,
      from: msg.from,
      payload: payloadText,
      raw: rawText,
      size: msg.payload.length,
    })
    
    stats.value.messagesReceived++
    stats.value.bytesReceived += msg.raw.length
    
    updateSubscriptions()
  }
  
  await client.value.subscribe(topic, handler)
  subscribedTopics.set(topic, { handler, messageCount })
  updateSubscriptions()
  log('Subscribed to topic', { topic })
}

async function subscribeToTopic() {
  if (!client.value) return
  const topic = newTopic.value.trim()
  if (!topic) return
  
  log('Manual subscription', { topic })
  await ensureSubscription(topic)
  newTopic.value = ''
}

async function unsubscribe(topic: string) {
  if (!client.value) return
  const info = subscribedTopics.get(topic)
  if (!info) return
  
  log('Unsubscribing from topic', { topic })
  await client.value.unsubscribe(topic, info.handler)
  subscribedTopics.delete(topic)
  delete topicDrafts.value[topic]
  delete topicMessages.value[topic]
  updateSubscriptions()
  log('Unsubscribed from topic', { topic })
}

// Publishing
async function publishWithCosmjs() {
  if (!client.value) throw new Error('Not connected')
  if (!cosmjsWallet.value) throw new Error('Set a CosmJS seed first')
  
  publishing.value = true
  signingStatus.value = true
  
  log('Publishing with CosmJS...', { address: cosmjsAddress.value })
  
  const signer = await createOfflineSignerSigner({ 
    wallet: cosmjsWallet.value, 
    address: cosmjsAddress.value || undefined 
  })
  cosmjsAddress.value = signer.address
  
  const topic = buildTopic(cosmjsAddress.value)
  await ensureSubscription(topic)
  
  const payloadJson = payload.value.trim() || '{}'
  const payloadBytes = uint8FromString(payloadJson)
  
  signingStatus.value = false
  publishingStatus.value = true
  
  log('Publishing message', { topic, bytes: payloadBytes.length })
  
  await client.value.publish({ topic, payload: payloadBytes, signer })
  
  // Get envelope for display - recreate for demo purposes
  const { createAdr36Envelope } = await import('./sdk/adr36')
  const envelope = await createAdr36Envelope({
    chainId: client.value!.chainId,
    topic,
    payload: payloadBytes,
    signer,
    peerId: client.value!.peerId,
  })
  
  const envelopeStr = JSON.stringify(envelope, null, 2)
  lastSignature.value = {
    signer: signer.address,
    method: 'CosmJS',
    envelope: envelopeStr,
  }
  
  addMessage({
    type: 'sent',
    topic,
    signer: signer.address,
    from: client.value.peerId,
    payload: payloadJson,
    raw: envelopeStr,
    size: payloadBytes.length,
  })
  
  stats.value.messagesSent++
  stats.value.bytesSent += payloadBytes.length
  
  log('Published successfully', { topic, signer: signer.address })
  
  publishing.value = false
  signingStatus.value = false
  publishingStatus.value = false
}

async function publishWithKeplr() {
  if (!client.value) throw new Error('Not connected')
  
  publishing.value = true
  signingStatus.value = true
  
  log('Publishing with Keplr...')
  
  const signer = await createKeplrSigner(client.value.chainId)
  keplrAddress.value = signer.address
  
  const topic = buildTopic(keplrAddress.value)
  await ensureSubscription(topic)
  
  const payloadJson = payload.value.trim() || '{}'
  const payloadBytes = uint8FromString(payloadJson)
  
  signingStatus.value = false
  publishingStatus.value = true
  
  log('Publishing message', { topic, bytes: payloadBytes.length })
  
  await client.value.publish({ topic, payload: payloadBytes, signer })
  
  // Get envelope for display - we already have it from publish, but recreate for display
  const { createAdr36Envelope: createAdr36EnvelopeKeplr } = await import('./sdk/adr36')
  const envelopeKeplr = await createAdr36EnvelopeKeplr({
    chainId: client.value!.chainId,
    topic,
    payload: payloadBytes,
    signer,
    peerId: client.value!.peerId,
  })
  
  const envelopeKeplrStr = JSON.stringify(envelopeKeplr, null, 2)
  lastSignature.value = {
    signer: signer.address,
    method: 'Keplr',
    envelope: envelopeKeplrStr,
  }
  
  addMessage({
    type: 'sent',
    topic,
    signer: signer.address,
    from: client.value.peerId,
    payload: payloadJson,
    raw: envelopeKeplrStr,
    size: payloadBytes.length,
  })
  
  stats.value.messagesSent++
  stats.value.bytesSent += payloadBytes.length
  
  log('Published successfully', { topic, signer: signer.address })
  
  publishing.value = false
  signingStatus.value = false
  publishingStatus.value = false
}

// Publish to a specific topic using the available signer (CosmJS preferred, else Keplr)
async function sendToTopic(topic: string) {
  if (!client.value) throw new Error('Not connected')
  
  log('Publishing to topic...', { topic })
  
  // Choose signer
  let signer: Awaited<ReturnType<typeof createOfflineSignerSigner>> | Awaited<ReturnType<typeof createKeplrSigner>>
  if (cosmjsWallet.value) {
    const s = await createOfflineSignerSigner({ wallet: cosmjsWallet.value, address: cosmjsAddress.value || undefined })
    cosmjsAddress.value = s.address
    signer = s
  } else if (keplrAvailable.value) {
    const s = await createKeplrSigner(client.value.chainId)
    keplrAddress.value = s.address
    signer = s
  } else {
    throw new Error('No signer available (set a CosmJS seed or enable Keplr)')
  }
  
  await ensureSubscription(topic)
  
  const payloadText = (topicDrafts.value[topic] || '').trim() || '{}'
  const payloadBytes = uint8FromString(payloadText)
  
  await client.value.publish({ topic, payload: payloadBytes, signer })
  
  // Recreate envelope for raw display
  const { createAdr36Envelope } = await import('./sdk/adr36')
  const env = await createAdr36Envelope({
    chainId: client.value!.chainId,
    topic,
    payload: payloadBytes,
    signer,
    peerId: client.value!.peerId,
  })
  const envStr = JSON.stringify(env, null, 2)
  
  const msgItem = {
    type: 'sent' as const,
    topic,
    signer: signer.address,
    from: client.value.peerId,
    payload: payloadText,
    raw: envStr,
    size: payloadBytes.length,
  }
  addMessage(msgItem)
  // Do not add to per-topic log; we want RX-only (GossipLog-backed) entries
  
  stats.value.messagesSent++
  stats.value.bytesSent += payloadBytes.length
  log('Published successfully', { topic, signer: signer.address })
}

// Messages
function addMessage(msg: Omit<MessageItem, 'id' | 'timestamp'>) {
  messages.value.unshift({
    ...msg,
    id: `${Date.now()}-${Math.random()}`,
    timestamp: Date.now(),
  })
}

function addTopicMessage(msg: Omit<MessageItem, 'id' | 'timestamp'>) {
  if (!topicMessages.value[msg.topic]) topicMessages.value[msg.topic] = []
  topicMessages.value[msg.topic].unshift({
    ...msg,
    id: `${Date.now()}-${Math.random()}`,
    timestamp: Date.now(),
  })
}

function clearMessages() {
  messages.value = []
  log('Cleared messages')
}

// Logging
function clearLog() {
  logOutput.value = ''
  log('Log cleared')
}

function exportLog() {
  const blob = new Blob([logOutput.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `dyson-demo-log-${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
  log('Exported log')
}

// Formatting
function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function formatUptime(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  if (hours > 0) return `${hours}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`
  return `${seconds}s`
}

// Lifecycle
onMounted(async () => {
  log('App mounted')
  keplrAvailable.value = typeof window.keplr !== 'undefined'
  
  // Auto-connect
  await handleConnect()
  if (mnemonic.value.trim()) {
    await useMnemonic()
  }
})

onUnmounted(async () => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
  await disconnect()
})
</script>



