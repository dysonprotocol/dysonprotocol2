<template>
  <div class="app">
    <h1>Dyson JS libp2p Demo</h1>
    <p class="intro">
      Demo connecting to Dyson peer via libp2p, using GossipSub for messaging, ADR-36 signing, and subscription management.
    </p>

    <!-- Connection Status -->
    <section class="section">
      <h2>Connection Status</h2>
      <div class="status-row">
        <button @click="handleConnect" :disabled="connecting || connected">
          {{ connected ? 'Disconnect' : 'Connect' }}
        </button>
        <span class="status" :class="statusClass">{{ connectionStatus }}</span>
        <span v-if="connected" class="peer-id">Peer ID: {{ peerId }}</span>
      </div>
      <div v-if="connected && bootstrap" class="bootstrap-info">
        <details>
          <summary>Bootstrap Info</summary>
          <pre>{{ JSON.stringify(bootstrap, null, 2) }}</pre>
        </details>
      </div>
    </section>

    <!-- Peer Connections -->
    <section v-if="connected" class="section">
      <h2>Peer Connections</h2>
      <div class="stats-row">
        <span>Connected: <strong>{{ connectedPeers.length }}</strong></span>
        <span>Total Known: <strong>{{ allPeers.length }}</strong></span>
        <span>Mesh Peers: <strong>{{ meshPeersCount }}</strong></span>
      </div>
      <div class="peers-list">
        <div v-for="peer in connectedPeers" :key="peer.id" class="peer-item">
          <span class="peer-id-small">{{ peer.id.slice(0, 12) }}...</span>
          <span class="peer-status connected">●</span>
          <span class="peer-addrs">{{ peer.addrs.length }} addr(s)</span>
        </div>
      </div>
    </section>

    <!-- GossipSub Mesh State -->
    <section v-if="connected" class="section">
      <h2>GossipSub Mesh State</h2>
      <div class="mesh-stats">
        <div>Total Pubsub Peers: <strong>{{ pubsubPeersCount }}</strong></div>
        <div>Active Topics: <strong>{{ subscriptions.length }}</strong></div>
      </div>
      <div v-if="meshDetails.length > 0" class="mesh-details">
        <div v-for="detail in meshDetails" :key="detail.topic" class="mesh-item">
          <strong>{{ detail.topic }}</strong>
          <span>Mesh: {{ detail.meshCount }}</span>
          <span>Subscribers: {{ detail.subscribersCount }}</span>
        </div>
      </div>
    </section>

    <!-- Wallet Management -->
    <section class="section">
      <h2>Wallet</h2>
      <div class="wallet-section">
        <label>
          Mnemonic seed (12 or 24 words)
          <textarea v-model="mnemonic" rows="3"></textarea>
        </label>
        <div class="button-row">
          <button @click="generateMnemonic">Generate Seed</button>
          <button @click="useMnemonic">Use Seed</button>
        </div>
        <div class="addresses">
          <p>CosmJS address: <code>{{ cosmjsAddress || '—' }}</code></p>
          <p>Keplr address: <code>{{ keplrAddress || (keplrAvailable ? '—' : 'Keplr not detected') }}</code></p>
        </div>
      </div>
    </section>

    <!-- Subscriptions -->
    <section v-if="connected" class="section">
      <h2>Subscriptions</h2>
      <div class="subscriptions-section">
        <div v-if="subscriptions.length === 0" class="empty">No active subscriptions</div>
        <div v-for="sub in subscriptions" :key="sub.topic" class="subscription-item">
          <div class="sub-header">
            <code>{{ sub.topic }}</code>
            <button @click="unsubscribe(sub.topic)" class="btn-small">Unsubscribe</button>
          </div>
          <div class="sub-info">Handlers: {{ sub.handlers }}, Messages: {{ sub.messageCount }}</div>
        </div>
        <div class="subscribe-form">
          <label>
            Subscribe to topic:
            <input v-model="newTopic" type="text" placeholder="/chainId/v1/address/suffix" />
          </label>
          <button @click="subscribeToTopic" :disabled="!newTopic.trim()">Subscribe</button>
        </div>
      </div>
    </section>

    <!-- Publish Message -->
    <section class="section">
      <h2>Publish Message</h2>
      <div class="publish-section">
        <label>
          Topic suffix (appended to <code>/CHAIN_ID/v1/&lt;address&gt;/</code>)
          <input v-model="topicSuffix" type="text" />
        </label>
        <label>
          Message JSON payload
          <textarea v-model="payload" rows="4"></textarea>
        </label>
        <div class="button-row">
          <button @click="publishWithCosmjs" :disabled="!canPublishCosmjs" :title="publishCosmjsTitle">
            Sign & Publish (CosmJS)
          </button>
          <button @click="publishWithKeplr" :disabled="!canPublishKeplr" :title="publishKeplrTitle">
            Sign & Publish (Keplr)
          </button>
        </div>
        <div v-if="publishing" class="publishing-status">
          <span v-if="signingStatus">Signing...</span>
          <span v-if="publishingStatus">Publishing...</span>
        </div>
      </div>
    </section>

    <!-- ADR36 Signing Info -->
    <section v-if="lastSignature" class="section">
      <h2>Last ADR36 Signature</h2>
      <div class="signature-info">
        <div><strong>Signer:</strong> {{ lastSignature.signer }}</div>
        <div><strong>Method:</strong> {{ lastSignature.method }}</div>
        <div><strong>Status:</strong> <span class="status-valid">Valid</span></div>
        <details>
          <summary>Envelope JSON</summary>
          <pre>{{ lastSignature.envelope }}</pre>
        </details>
      </div>
    </section>

    <!-- Messages -->
    <section class="section">
      <h2>Messages</h2>
      <div class="messages-controls">
        <button @click="clearMessages">Clear</button>
        <input v-model="messageFilter" type="text" placeholder="Filter by topic or signer..." />
        <select v-model="messageFilterType">
          <option value="all">All</option>
          <option value="sent">Sent</option>
          <option value="received">Received</option>
        </select>
      </div>
      <div class="messages-list">
        <div v-for="msg in filteredMessages" :key="msg.id" class="message-item" :class="msg.type">
          <div class="message-header">
            <span class="message-type">{{ msg.type === 'sent' ? 'TX' : 'RX' }}</span>
            <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
            <span class="message-signer">{{ msg.signer }}</span>
          </div>
          <div class="message-topic"><code>{{ msg.topic }}</code></div>
          <div class="message-payload">{{ msg.payload }}</div>
          <div class="message-meta">
            <span>From: {{ msg.from }}</span>
            <span>Size: {{ msg.size }} bytes</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Statistics -->
    <section v-if="connected" class="section">
      <h2>Statistics</h2>
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-label">Messages Sent</div>
          <div class="stat-value">{{ stats.messagesSent }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Messages Received</div>
          <div class="stat-value">{{ stats.messagesReceived }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Bytes Sent</div>
          <div class="stat-value">{{ formatBytes(stats.bytesSent) }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Bytes Received</div>
          <div class="stat-value">{{ formatBytes(stats.bytesReceived) }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Uptime</div>
          <div class="stat-value">{{ formatUptime(stats.uptime) }}</div>
        </div>
      </div>
    </section>

    <!-- Debug Log -->
    <section class="section">
      <h2>Debug Log</h2>
      <div class="log-controls">
        <button @click="clearLog">Clear Log</button>
        <button @click="exportLog">Export Log</button>
      </div>
      <pre class="debug-log" ref="logRef">{{ logOutput }}</pre>
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
const connectedPeers = ref<Array<{ id: string; addrs: string[] }>>([])
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

// Messages
interface MessageItem {
  id: string
  type: 'sent' | 'received'
  topic: string
  signer: string
  from: string
  payload: string
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

const statusClass = computed(() => {
  if (connected.value) return 'status-connected'
  if (connecting.value) return 'status-connecting'
  return 'status-disconnected'
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
    try {
      const subscribers = pubsub.getSubscribers(sub.topic) || []
      // Try to get mesh peers if available (GossipSub specific)
      const mesh = (pubsub.getMeshPeers && typeof pubsub.getMeshPeers === 'function' && pubsub.getMeshPeers(sub.topic)) || []
      return {
        topic: sub.topic,
        meshCount: mesh.length,
        subscribersCount: subscribers.length,
      }
    } catch (err) {
      console.warn('Failed to get mesh details', err)
      return { topic: sub.topic, meshCount: 0, subscribersCount: 0 }
    }
  })
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
  
  try {
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

    const peerStore = (client.value.libp2p as any).peerStore
    if (peerStore) {
      const all: Array<{ id: string; addrs: string[] }> = []
      const connected: Array<{ id: string; addrs: string[] }> = []
      
      for (const peer of peerStore.peers.values()) {
        const addrs = peer.addresses.map((a: any) => a.multiaddr.toString())
        const peerInfo = { id: peer.id.toString(), addrs }
        all.push(peerInfo)
        
        const conns = client.value.libp2p.getPeers()
        if (conns.includes(peer.id)) {
          connected.push(peerInfo)
        }
      }
      
      allPeers.value = all
      connectedPeers.value = connected
    }
  } catch (err) {
    logError('Failed to update peers', err)
  }
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
  
  try {
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
    
  } catch (err) {
    logError('Connection failed', err)
    connecting.value = false
    connected.value = false
  }
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
  
  try {
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
  } catch (err) {
    logError('Failed to setup event listeners', err)
  }
}

// Wallet
async function generateMnemonic() {
  log('Generating mnemonic...')
  try {
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
  } catch (err) {
    logError('Failed to generate mnemonic', err)
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
  
  try {
    cosmjsWallet.value = await DirectSecp256k1HdWallet.fromMnemonic(trimmed, { prefix: DEFAULT_PREFIX })
    const [account] = await cosmjsWallet.value.getAccounts()
    cosmjsAddress.value = account.address
    log('Loaded mnemonic', { address: cosmjsAddress.value })
    
    if (connected.value && cosmjsAddress.value) {
      const topic = buildTopic(cosmjsAddress.value)
      await ensureSubscription(topic)
    }
  } catch (err) {
    logError('Failed to load mnemonic', err)
    cosmjsWallet.value = undefined
    cosmjsAddress.value = ''
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
  
  const messageCount = 0
  const handler = (msg: DysonMessage) => {
    const info = subscribedTopics.get(topic)
    if (info) info.messageCount++
    
    const payloadText = msg.payloadJson !== undefined 
      ? JSON.stringify(msg.payloadJson) 
      : uint8ToString(msg.payload)
    
    log('RX message', { topic: msg.topic, from: msg.from, payload: payloadText })
    
    addMessage({
      type: 'received',
      topic: msg.topic,
      signer: msg.from,
      from: msg.from,
      payload: payloadText,
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
  updateSubscriptions()
  log('Unsubscribed from topic', { topic })
}

// Publishing
async function publishWithCosmjs() {
  if (!client.value) throw new Error('Not connected')
  if (!cosmjsWallet.value) throw new Error('Set a CosmJS seed first')
  
  publishing.value = true
  signingStatus.value = true
  
  try {
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
    
    lastSignature.value = {
      signer: signer.address,
      method: 'CosmJS',
      envelope: JSON.stringify(envelope, null, 2),
    }
    
    addMessage({
      type: 'sent',
      topic,
      signer: signer.address,
      from: client.value.peerId,
      payload: payloadJson,
      size: payloadBytes.length,
    })
    
    stats.value.messagesSent++
    stats.value.bytesSent += payloadBytes.length
    
    log('Published successfully', { topic })
    
  } catch (err) {
    logError('Publish failed', err)
    throw err
  } finally {
    publishing.value = false
    signingStatus.value = false
    publishingStatus.value = false
  }
}

async function publishWithKeplr() {
  if (!client.value) throw new Error('Not connected')
  
  publishing.value = true
  signingStatus.value = true
  
  try {
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
    
    lastSignature.value = {
      signer: signer.address,
      method: 'Keplr',
      envelope: JSON.stringify(envelopeKeplr, null, 2),
    }
    
    addMessage({
      type: 'sent',
      topic,
      signer: signer.address,
      from: client.value.peerId,
      payload: payloadJson,
      size: payloadBytes.length,
    })
    
    stats.value.messagesSent++
    stats.value.bytesSent += payloadBytes.length
    
    log('Published successfully', { topic })
    
  } catch (err) {
    logError('Publish failed', err)
    throw err
  } finally {
    publishing.value = false
    signingStatus.value = false
    publishingStatus.value = false
  }
}

// Messages
function addMessage(msg: Omit<MessageItem, 'id' | 'timestamp'>) {
  messages.value.unshift({
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
  try {
    await handleConnect()
    if (mnemonic.value.trim()) {
      await useMnemonic()
    }
  } catch (err) {
    logError('Auto-connect failed', err)
  }
})

onUnmounted(async () => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
  await disconnect()
})
</script>

<style scoped>
.app {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  font-family: system-ui, sans-serif;
}

.intro {
  color: #666;
  margin-bottom: 2rem;
}

.section {
  margin-bottom: 2rem;
  padding: 1.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fafafa;
}

.section h2 {
  margin-top: 0;
  margin-bottom: 1rem;
  font-size: 1.25rem;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.status {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-weight: 500;
}

.status-connected {
  background: #d4edda;
  color: #155724;
}

.status-connecting {
  background: #fff3cd;
  color: #856404;
}

.status-disconnected {
  background: #f8d7da;
  color: #721c24;
}

.peer-id {
  font-family: monospace;
  font-size: 0.9rem;
  color: #666;
}

.bootstrap-info {
  margin-top: 1rem;
}

.bootstrap-info pre {
  background: #f5f5f5;
  padding: 1rem;
  border-radius: 4px;
  overflow: auto;
  max-height: 300px;
}

.stats-row {
  display: flex;
  gap: 2rem;
  margin-bottom: 1rem;
}

.peers-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.peer-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem;
  background: white;
  border-radius: 4px;
}

.peer-id-small {
  font-family: monospace;
  font-size: 0.85rem;
}

.peer-status {
  font-size: 1.2rem;
}

.peer-status.connected {
  color: #28a745;
}

.peer-addrs {
  font-size: 0.85rem;
  color: #666;
}

.mesh-stats {
  display: flex;
  gap: 2rem;
  margin-bottom: 1rem;
}

.mesh-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.mesh-item {
  display: flex;
  gap: 1rem;
  padding: 0.5rem;
  background: white;
  border-radius: 4px;
}

.wallet-section label {
  display: block;
  margin-bottom: 0.5rem;
}

.wallet-section textarea {
  width: 100%;
  min-height: 80px;
  font-family: monospace;
  font-size: 0.9rem;
}

.button-row {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}

button {
  padding: 0.5rem 1rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}

button:hover:not(:disabled) {
  background: #f0f0f0;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-small {
  padding: 0.25rem 0.5rem;
  font-size: 0.85rem;
}

.addresses {
  margin-top: 1rem;
}

.addresses code {
  font-family: monospace;
  background: #f5f5f5;
  padding: 0.25rem 0.5rem;
  border-radius: 2px;
}

.subscriptions-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.subscription-item {
  padding: 1rem;
  background: white;
  border-radius: 4px;
  border: 1px solid #ddd;
}

.sub-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.sub-header code {
  font-family: monospace;
  font-size: 0.9rem;
}

.sub-info {
  font-size: 0.85rem;
  color: #666;
}

.subscribe-form {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
  margin-top: 1rem;
}

.subscribe-form label {
  flex: 1;
}

.subscribe-form input {
  width: 100%;
  padding: 0.5rem;
  font-family: monospace;
  font-size: 0.9rem;
}

.publish-section label {
  display: block;
  margin-bottom: 0.5rem;
}

.publish-section textarea {
  width: 100%;
  min-height: 100px;
  font-family: monospace;
  font-size: 0.9rem;
}

.publishing-status {
  margin-top: 0.5rem;
  color: #666;
  font-size: 0.9rem;
}

.signature-info {
  background: white;
  padding: 1rem;
  border-radius: 4px;
}

.signature-info > div {
  margin-bottom: 0.5rem;
}

.status-valid {
  color: #28a745;
  font-weight: 500;
}

.signature-info pre {
  background: #f5f5f5;
  padding: 1rem;
  border-radius: 4px;
  overflow: auto;
  max-height: 400px;
  margin-top: 1rem;
}

.messages-controls {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  align-items: center;
}

.messages-controls input {
  flex: 1;
  padding: 0.5rem;
}

.messages-controls select {
  padding: 0.5rem;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 500px;
  overflow-y: auto;
}

.message-item {
  padding: 1rem;
  background: white;
  border-radius: 4px;
  border-left: 4px solid #ddd;
}

.message-item.sent {
  border-left-color: #007bff;
}

.message-item.received {
  border-left-color: #28a745;
}

.message-header {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

.message-type {
  font-weight: bold;
  padding: 0.25rem 0.5rem;
  border-radius: 3px;
  background: #f0f0f0;
}

.message-time {
  color: #666;
}

.message-signer {
  font-family: monospace;
  font-size: 0.85rem;
  color: #007bff;
}

.message-topic {
  margin-bottom: 0.5rem;
}

.message-topic code {
  font-family: monospace;
  font-size: 0.85rem;
  background: #f5f5f5;
  padding: 0.25rem 0.5rem;
  border-radius: 2px;
}

.message-payload {
  font-family: monospace;
  font-size: 0.9rem;
  background: #f9f9f9;
  padding: 0.5rem;
  border-radius: 3px;
  margin-bottom: 0.5rem;
  white-space: pre-wrap;
  word-break: break-all;
}

.message-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.85rem;
  color: #666;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.stat-item {
  background: white;
  padding: 1rem;
  border-radius: 4px;
  text-align: center;
}

.stat-label {
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: bold;
  color: #007bff;
}

.log-controls {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.debug-log {
  background: #1e1e1e;
  color: #0f0;
  padding: 1rem;
  border-radius: 4px;
  overflow: auto;
  max-height: 400px;
  font-family: 'Courier New', monospace;
  font-size: 0.85rem;
  line-height: 1.4;
}

.empty {
  color: #666;
  font-style: italic;
  padding: 1rem;
}

code {
  font-family: 'Courier New', monospace;
}

pre {
  margin: 0;
}
</style>

