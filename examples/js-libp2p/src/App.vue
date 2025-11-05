<template>
  <div class="min-h-screen bg-base-200">
    <!-- Header Bar -->
    <header class="bg-base-100 border-b border-base-300 p-4">
      <div class="container mx-auto flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold">Dyson libp2p Demo</h1>
          <button @click="handleConnect" :disabled="connecting" :class="connected ? 'btn btn-error btn-sm' : 'btn btn-primary btn-sm'">
            {{ connected ? 'Disconnect' : 'Connect' }}
          </button>
          <span :class="connected ? 'badge badge-success' : 'badge badge-error'">{{ connectionStatus }}</span>
          <span v-if="connected && peerId" class="badge badge-outline text-xs">Peer: <code class="break-all">{{ peerId }}</code></span>
        </div>
        <div class="flex items-center gap-4">
          <div v-if="cosmjsAddress" class="badge badge-info">CosmJS: <code class="ml-1 text-xs break-all">{{ cosmjsAddress }}</code></div>
          <div v-if="keplrAvailable && keplrAddress" class="badge badge-secondary">Keplr: <code class="ml-1 text-xs break-all">{{ keplrAddress }}</code></div>
          <details class="dropdown dropdown-end">
            <summary class="btn btn-sm btn-ghost">Wallet</summary>
            <div class="dropdown-content menu bg-base-100 shadow-xl rounded-box w-96 p-4 z-50">
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Mnemonic</span>
                </label>
                <textarea v-model="mnemonic" rows="3" class="textarea textarea-bordered textarea-sm"></textarea>
              </div>
              <div class="flex gap-2 mt-2">
                <button @click="generateMnemonic" class="btn btn-sm btn-secondary">Generate</button>
                <button @click="useMnemonic" class="btn btn-sm btn-primary">Use Seed</button>
              </div>
            </div>
          </details>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="container mx-auto p-4" v-if="connected">
      <div class="grid grid-cols-12 gap-4">
        <!-- Left: Peers (Primary Focus) -->
          <section class="col-span-12 lg:col-span-6">
            <div class="card bg-base-100 shadow-xl ">
            <div class="card-body">
              <h2 class="card-title">Peers</h2>
              
              <!-- Peer Stats -->
              <div class="stats stats-horizontal shadow w-full">
                <div class="stat py-2">
                  <div class="stat-title text-xs">Connected</div>
                  <div class="stat-value text-lg text-primary">{{ connectedPeers.length }}</div>
                </div>
                <div class="stat py-2">
                  <div class="stat-title text-xs">Known</div>
                  <div class="stat-value text-lg text-info">{{ allPeers.length }}</div>
                </div>
                <div class="stat py-2">
                  <div class="stat-title text-xs">Mesh</div>
                  <div class="stat-value text-lg text-secondary">{{ meshPeersCount }}</div>
                </div>
                <div class="stat py-2">
                  <div class="stat-title text-xs">Pubsub</div>
                  <div class="stat-value text-lg text-accent">{{ pubsubPeersCount }}</div>
                </div>
              </div>

              <!-- Peer List -->
              <div class="mt-4 space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto">
                <div v-for="p in allPeers" :key="p.id" class="card card-compact bg-base-200">
                  <div class="card-body p-3">
                    <div class="flex flex-wrap items-center gap-2 mb-2">
                      <code class="badge badge-neutral text-xs font-mono break-all">{{ p.id }}</code>
                      <template v-if="connectedById[p.id]">
                        <span class="badge badge-outline badge-sm">{{ connectedById[p.id].direction || '—' }}</span>
                        <span class="badge badge-outline badge-sm">{{ connectedById[p.id].status || '—' }}</span>
                      </template>
                    </div>
                    <div class="text-xs text-base-content/70 break-all">
                      <code>{{ connectedById[p.id]?.remoteAddr || (p.addrs[0] || '—') }}</code>
                    </div>
                    <div v-if="connectedById[p.id]" class="text-xs text-base-content/50 mt-1">
                      {{ connectedById[p.id].streams }} streams · {{ formatUptime(connectedById[p.id].openedMs) }} ago
                    </div>
                  </div>
                </div>
                <div v-if="allPeers.length === 0" class="text-center text-base-content/50 py-8">
                  No peers discovered yet
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Center: Topics & Messages -->
        <section class="col-span-12 lg:col-span-6">

          <div class="card bg-base-100 shadow-xl mb-4">
            <div class="card-body">
              <h2 class="card-title">Publish</h2>
              
              <div class="form-control">
                <label class="label">
                  <span class="label-text text-xs">Full Topic</span>
                  <a @click.prevent="prependTopicPrefix" class="link link-primary text-xs" v-if="connected && client && (cosmjsAddress || keplrAddress)">
                    /{{ client.chainId }}/v1/{{ cosmjsAddress || keplrAddress || '...' }}/
                  </a>
                </label>
                <input v-model="fullTopic" type="text" placeholder="/{chainId}/v1/{address}/{suffix}" class="input input-bordered input-sm" />
              </div>
              
              <div class="form-control mt-4">
                <label class="label">
                  <span class="label-text text-xs">Payload (JSON or text)</span>
                </label>
                <textarea v-model="payload" rows="3" class="textarea textarea-bordered textarea-sm"></textarea>
              </div>
              
              <div class="flex flex-col gap-2 mt-4">
                <button @click="publishWithCosmjs" :disabled="!canPublishCosmjs" :title="publishCosmjsTitle" class="btn btn-sm btn-primary">
                  Publish (CosmJS)
                </button>
                <button @click="publishWithKeplr" :disabled="!canPublishKeplr" :title="publishKeplrTitle" class="btn btn-sm btn-secondary">
                  Publish (Keplr)
                </button>
              </div>

              <div v-if="publishing" class="alert alert-info alert-sm mt-4">
                <span v-if="signingStatus">Signing...</span>
                <span v-if="publishingStatus">Publishing...</span>
              </div>

              <div v-if="lastSignature" class="mt-4 p-2 bg-base-200 rounded">
                <div class="text-xs space-y-1">
                  <div><strong>Signer:</strong> <code class="text-xs break-all">{{ lastSignature.signer }}</code></div>
                  <div><strong>Method:</strong> {{ lastSignature.method }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="card bg-base-100 shadow-xl flex flex-col">
            <div class="card-body flex-1 flex flex-col">
              <h2 class="card-title">Topics & Messages</h2>
              
              <!-- Topics Section -->
              <div class="mb-4">
                <div class="flex gap-2 mb-2">
                  <input v-model="newTopic" @keyup.enter="subscribeToTopic" type="text" placeholder="Topic suffix or full topic" class="input input-bordered input-sm flex-1" />
                  <button @click="subscribeToTopic" :disabled="!newTopic.trim()" class="btn btn-sm btn-primary">Subscribe</button>
                </div>
                <div class="space-y-2 max-h-32 overflow-y-auto">
                  <div v-for="sub in subscriptions" :key="sub.topic" class="flex items-center justify-between bg-base-200 p-2 rounded">
                    <code class="text-xs flex-1 break-all">{{ sub.topic }}</code>
                    <div class="flex items-center gap-2">

                      <button @click="unsubscribe(sub.topic)" class="btn btn-xs btn-error">×</button>
                    </div>
                  </div>
                  <div v-if="subscriptions.length === 0" class="text-xs text-base-content/50 text-center py-2">
                    No subscriptions
                  </div>
                </div>
              </div>

              <!-- Messages for Selected Topic -->
              <div class="flex-1 flex flex-col min-h-0">
                <div class="flex items-center justify-between mb-2">
                  <h3 class="text-sm font-semibold">Messages</h3>
                  <select v-model="selectedTopic" class="select select-bordered select-sm w-48">
                    <option value="">All topics</option>
                    <option v-for="sub in subscriptions" :key="sub.topic" :value="sub.topic">{{ sub.topic }}</option>
                  </select>
                </div>
                <div class="flex-1 overflow-y-auto space-y-2">
                  <div v-for="msg in filteredTopicMessages" :key="msg.id" class="card card-compact bg-base-200">
                    <div class="card-body p-2">
                      <div class="flex items-center gap-2 mb-1">
                        Topic <code class="text-xs text-primary break-all">{{ msg.topic }}</code>
                      </div>
                      <div class="text-sm mb-2 overflow-x-auto whitespace-nowrap">{{ msg.payload }}</div>
                      <details class="collapse collapse-arrow bg-base-300">
                        <summary class="collapse-title text-xs min-h-0">Details</summary>
                        <div class="collapse-content p-2">
                          <pre class="bg-base-100 p-2 rounded text-xs overflow-x-auto">{{ msg }}</pre>
                        </div>
                      </details>
                    </div>
                  </div>
                  <div v-if="filteredTopicMessages.length === 0" class="text-center text-base-content/50 py-8 text-sm">
                    No messages
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        
      </div>
    </main>

    <!-- Disconnected State -->
    <main v-else class="container mx-auto p-6">
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body text-center py-12">
          <p class="text-base-content/70">Click Connect to start</p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
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
const fullTopic = ref('')
const payload = ref('{"text":"Hello Dyson"}')
const publishing = ref(false)
const signingStatus = ref(false)
const publishingStatus = ref(false)
const lastSignature = ref<{ signer: string; method: string; envelope: string } | null>(null)

// Subscriptions
const subscriptions = ref<Array<{ topic: string; handlers: number; messageCount: number }>>([])
const subscribedTopics = new Map<string, { handler: (msg: DysonMessage) => void; messageCount: number }>()
const newTopic = ref('')
const selectedTopic = ref('')

// Per-topic UI state
const topicMessages = ref<Record<string, MessageItem[]>>({})

// Messages
interface MessageItem {
  id: string
  topic: string
  signer: string
  from: string
  payload: string
  raw?: string
  timestamp: number
  size: number
}
const messages = ref<MessageItem[]>([])

// Statistics
const stats = ref({
  messagesSent: 0,
  messagesReceived: 0,
  bytesSent: 0,
  bytesReceived: 0,
  uptime: 0,
})

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

const filteredTopicMessages = computed(() => {
  let filtered = messages.value
  if (selectedTopic.value) {
    filtered = filtered.filter(m => m.topic === selectedTopic.value)
  }
  return filtered.sort((a, b) => b.timestamp - a.timestamp)
})

const connectedById = computed<Record<string, any>>(() => {
  const obj: Record<string, any> = {}
  for (const p of connectedPeers.value) obj[p.id] = p
  return obj
})

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

    let protocols: string[] = []
    const protoBook = peerStore?.protoBook
    if (protoBook?.get) {
      const p = protoBook.get(primary?.remotePeer)
      if (Array.isArray(p)) protocols = p
    }

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
  
  client.value = await createDysonClient()
  peerId.value = client.value.peerId
  bootstrap.value = client.value.bootstrap
  connectionStartTime.value = Date.now()
  
  connected.value = true
  connecting.value = false
  
  setupEventListeners()
  updatePeers()
  
  if (cosmjsAddress.value) {
    const topic = buildTopic(cosmjsAddress.value)
    await ensureSubscription(topic)
  }
  
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
}

function setupEventListeners() {
  if (!client.value) return
  
  client.value.libp2p.addEventListener('peer:connect', () => updatePeers())
  client.value.libp2p.addEventListener('peer:disconnect', () => updatePeers())
  client.value.libp2p.addEventListener('connection:open', () => updatePeers())
  client.value.libp2p.addEventListener('connection:close', () => updatePeers())
  client.value.libp2p.addEventListener('peer:discovery', () => updatePeers())
}

// Wallet
async function generateMnemonic() {
  const wallet = await DirectSecp256k1HdWallet.generate(12, { prefix: DEFAULT_PREFIX })
  mnemonic.value = wallet.mnemonic
  cosmjsWallet.value = wallet
  const [account] = await wallet.getAccounts()
  cosmjsAddress.value = account.address
  
  if (connected.value && cosmjsAddress.value) {
    const topic = buildTopic(cosmjsAddress.value)
    await ensureSubscription(topic)
  }
}

async function useMnemonic() {
  const trimmed = mnemonic.value.trim()
  if (!trimmed) {
    cosmjsWallet.value = undefined
    cosmjsAddress.value = ''
    return
  }
  
  cosmjsWallet.value = await DirectSecp256k1HdWallet.fromMnemonic(trimmed, { prefix: DEFAULT_PREFIX })
  const [account] = await cosmjsWallet.value.getAccounts()
  cosmjsAddress.value = account.address
  
  if (connected.value && cosmjsAddress.value) {
    const topic = buildTopic(cosmjsAddress.value)
    await ensureSubscription(topic)
  }
}

// Subscriptions
function buildTopic(address: string): string {
  if (!client.value) throw new Error('Not connected')
  return client.value.buildTopic(address, 'demo')
}

function prependTopicPrefix() {
  if (!client.value) return
  const address = cosmjsAddress.value || keplrAddress.value
  if (!address) return
  const prefix = `/chain-${client.value.chainId}/v1/${address}/`
  fullTopic.value = prefix + fullTopic.value
}

async function ensureSubscription(topic: string) {
  if (!client.value) return
  if (subscribedTopics.has(topic)) return
  
  if (!topicMessages.value[topic]) topicMessages.value[topic] = []
  
  const messageCount = 0
  const handler = (msg: DysonMessage) => {
    const info = subscribedTopics.get(topic)
    if (info) info.messageCount++
    
    const payloadText = msg.payloadJson !== undefined 
      ? JSON.stringify(msg.payloadJson) 
      : uint8ToString(msg.payload)
    
    let signerAddress = msg.from
    if (msg.envelope) {
      signerAddress = msg.envelope.body?.messages?.[0]?.signer || msg.from
    }
    
    const rawText = msg.envelope ? JSON.stringify(msg.envelope, null, 2) : uint8ToString(msg.raw)
    
    addMessage({
      topic: msg.topic,
      signer: signerAddress,
      from: msg.from,
      payload: payloadText,
      raw: rawText,
      size: msg.payload.length,
    })
    
    addTopicMessage({
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
}

async function subscribeToTopic() {
  if (!client.value) return
  const topic = newTopic.value.trim()
  if (!topic) return
  
  await ensureSubscription(topic)
  newTopic.value = ''
}

async function unsubscribe(topic: string) {
  if (!client.value) return
  const info = subscribedTopics.get(topic)
  if (!info) return
  
  await client.value.unsubscribe(topic, info.handler)
  subscribedTopics.delete(topic)
  delete topicMessages.value[topic]
  if (selectedTopic.value === topic) selectedTopic.value = ''
  updateSubscriptions()
}

// Publishing
async function publishWithCosmjs() {
  if (!client.value) throw new Error('Not connected')
  if (!cosmjsWallet.value) throw new Error('Set a CosmJS seed first')
  
  publishing.value = true
  signingStatus.value = true
  
  const signer = await createOfflineSignerSigner({ 
    wallet: cosmjsWallet.value, 
    address: cosmjsAddress.value || undefined 
  })
  cosmjsAddress.value = signer.address
  
  const topic = fullTopic.value.trim()
  if (!topic) throw new Error('Topic is required')
  await ensureSubscription(topic)
  
  const payloadJson = payload.value.trim() || '{}'
  const payloadBytes = uint8FromString(payloadJson)
  
  signingStatus.value = false
  publishingStatus.value = true
  
  await client.value.publish({ topic, payload: payloadBytes, signer })
  
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
  
  
  stats.value.messagesSent++
  stats.value.bytesSent += payloadBytes.length
  
  publishing.value = false
  signingStatus.value = false
  publishingStatus.value = false
}

async function publishWithKeplr() {
  if (!client.value) throw new Error('Not connected')
  
  publishing.value = true
  signingStatus.value = true
  
  const signer = await createKeplrSigner(client.value.chainId)
  keplrAddress.value = signer.address
  
  const topic = fullTopic.value.trim()
  if (!topic) throw new Error('Topic is required')
  await ensureSubscription(topic)
  
  const payloadJson = payload.value.trim() || '{}'
  const payloadBytes = uint8FromString(payloadJson)
  
  signingStatus.value = false
  publishingStatus.value = true
  
  await client.value.publish({ topic, payload: payloadBytes, signer })
  
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
    method: 'Keplr',
    envelope: envelopeStr,
  }
  
  
  stats.value.messagesSent++
  stats.value.bytesSent += payloadBytes.length
  
  publishing.value = false
  signingStatus.value = false
  publishingStatus.value = false
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

// Formatting
function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
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
  keplrAvailable.value = typeof window.keplr !== 'undefined'
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
