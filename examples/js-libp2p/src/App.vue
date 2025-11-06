<template>
  <div class="min-h-screen bg-base-200">
    <header class="bg-base-100 border-b border-base-300 p-4">
      <div class="container mx-auto flex items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-semibold">Dyson Chat</h1>
          <button @click="onConnectClick" :disabled="connecting" :class="connected ? 'btn btn-error btn-sm' : 'btn btn-primary btn-sm'">
            {{ connected ? 'Disconnect' : 'Connect' }}
          </button>
          <span :class="connected ? 'badge badge-success' : 'badge badge-error'">{{ statusText }}</span>
          <span v-if="connected && peerId" class="badge badge-outline text-xs">PeerId: <code class="break-all">{{ peerId }}</code></span>
          <span v-if="address" class="badge badge-outline text-xs">Addr: <code class="break-all">{{ address }}</code></span>
        </div>
        <div class="flex items-center gap-2">
          <details class="dropdown dropdown-end">
            <summary class="btn btn-ghost btn-sm">Wallet</summary>
            <div class="dropdown-content menu bg-base-100 shadow-xl rounded-box w-96 p-4 z-50">
              <div class="form-control">
                <label class="label"><span class="label-text">Mnemonic</span></label>
                <textarea v-model="mnemonic" rows="3" class="textarea textarea-bordered textarea-sm"></textarea>
              </div>
              <div class="flex gap-2 mt-2">
                <button @click="generateMnemonic" class="btn btn-sm">Generate</button>
                <button @click="applyMnemonic" class="btn btn-sm btn-primary">Use Seed</button>
              </div>
              <div v-if="address" class="mt-2 text-xs">Address: <code class="break-all">{{ address }}</code></div>
            </div>
          </details>
        </div>
      </div>
    </header>

    <main v-if="connected" class="container mx-auto p-4">
      <div class="grid grid-cols-12 gap-4">
        <!-- Left: Topic management -->
        <section class="col-span-12 md:col-span-3">
          <div class="card bg-base-100 shadow">
            <div class="card-body gap-3">
              <h2 class="card-title">Topics</h2>
              <div class="form-control">
                <label class="label"><span class="label-text text-xs">Room name</span></label>
                <input v-model="room" @keyup.enter="joinRoom" type="text" placeholder="e.g. general" class="input input-bordered input-sm" />
              </div>
              <button @click="joinRoom" :disabled="!room.trim()" class="btn btn-sm btn-primary">Join</button>
              <div class="divider my-1"></div>
              <div class="space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto">
                <div
                  v-for="t in topics"
                  :key="t"
                  class="flex items-center gap-2 p-2 rounded cursor-pointer hover:bg-base-200"
                  :class="{ 'bg-base-200': t === selectedTopic }"
                  @click="selectTopic(t)"
                >
                  <code class="text-xs break-all flex-1">{{ t }}</code>
                  <button class="btn btn-xs btn-error" @click.stop="leaveTopic(t)">×</button>
                </div>
                <div v-if="topics.length === 0" class="text-xs text-base-content/60 text-center py-2">No topics joined</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Center: Messages -->
        <section class="col-span-12 md:col-span-6">
          <div class="card bg-base-100 shadow h-[calc(100vh-160px)]">
            <div class="card-body gap-3 h-full">
              <div class="flex items-center justify-between">
                <h2 class="card-title">
                  Messages<span v-if="selectedTopic">: <code class="break-all text-sm">{{ selectedTopic }}</code></span>
                </h2>
              </div>

              <div class="flex-1 min-h-0 overflow-y-auto space-y-2" ref="scrollArea">
                <div v-for="m in messages" :key="m.id" class="card card-compact bg-base-200">
                  <div class="card-body p-2">
                    <div class="flex items-center gap-2 text-xs">
                      <span class="badge badge-ghost">{{ short(m.signer) }}</span>
                      <span class="text-base-content/60">from</span>
                      <code class="text-xs break-all">{{ short(m.from) }}</code>
                      <span class="text-base-content/60">at</span>
                      <span>{{ formatTime(m.ts) }}</span>
                    </div>
                    <div class="mt-1 text-sm break-words whitespace-pre-wrap">{{ m.text }}</div>
                  </div>
                </div>
                <div v-if="messages.length === 0" class="text-center text-sm text-base-content/60 py-8">No messages</div>
              </div>

              <div class="form-control">
                <textarea v-model="draft" rows="2" class="textarea textarea-bordered textarea-sm" placeholder="Write a message..." @keydown.enter.prevent="send"></textarea>
                <div class="mt-2 flex gap-2 justify-end">
                  <button class="btn btn-sm" @click="clearDraft" :disabled="!draft.trim()">Clear</button>
                  <button class="btn btn-sm btn-primary" @click="send" :disabled="!canSend">Send</button>
                </div>
                <div v-if="!canSend" class="mt-1 text-xs text-base-content/60">
                  {{ sendDisabledReason }}
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Right: Peers and memberships -->
        <section class="col-span-12 md:col-span-3">
          <div class="card bg-base-100 shadow">
            <div class="card-body gap-3">
              <h2 class="card-title">Peers</h2>
              <div class="max-h-[calc(100vh-300px)] overflow-y-auto space-y-2">
                <div v-for="p in peers" :key="p.id" class="p-2 bg-base-200 rounded">
                  <div class="text-xs break-all"><code>{{ p.id }}</code></div>
                  <div class="mt-1 flex flex-wrap gap-1">
                    <span v-for="t in p.topics" :key="p.id + t" class="badge badge-ghost text-[10px]"><code>{{ shortTopic(t) }}</code></span>
                  </div>
                </div>
                <div v-if="peers.length === 0" class="text-xs text-base-content/60 text-center py-2">No peers</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>

    <main v-else class="container mx-auto p-6">
      <div class="card bg-base-100 shadow">
        <div class="card-body text-center py-12">
          <p class="text-base-content/70">Click Connect to start</p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { DirectSecp256k1HdWallet } from '@cosmjs/proto-signing'
import { fromString as uint8FromString } from 'uint8arrays/from-string'
import type { DysonClient, DysonMessage } from './sdk/types'
import { createDysonClient } from './sdk/client'
import { createOfflineSignerSigner } from './sdk/signers'

// connection
const connecting = ref(false)
const connected = ref(false)
const client = ref<DysonClient | null>(null)
const peerId = ref('')
const statusText = computed(() => (connecting.value ? 'Connecting…' : connected.value ? 'Connected' : 'Disconnected'))

// wallet (minimal)
const mnemonic = ref('')
const address = ref('')
let wallet: DirectSecp256k1HdWallet | null = null

// topics and messages
const topics = ref<string[]>([])
const selectedTopic = ref('')
const room = ref('')
const draft = ref('')

interface ChatItem { id: string; topic: string; text: string; from: string; signer: string; ts: number }
const byTopic = reactive<Record<string, ChatItem[]>>({})
const messages = computed(() => selectedTopic.value ? (byTopic[selectedTopic.value] ?? []) : [])

// peers view
interface PeerEntry { id: string; topics: string[] }
const peers = ref<PeerEntry[]>([])
let peersTimer: ReturnType<typeof setInterval> | null = null

// connect/disconnect
async function onConnectClick() {
  if (connected.value) return disconnect()
  connecting.value = true
  const c = await createDysonClient()
  client.value = c
  peerId.value = c.peerId
  connected.value = true
  connecting.value = false
  startPeersRefresh()
}

async function disconnect() {
  if (client.value) await client.value.stop()
  client.value = null
  connected.value = false
  connecting.value = false
  topics.value = []
  selectedTopic.value = ''
  byTopic.value = {} as any
  stopPeersRefresh()
}

// wallet helpers
async function generateMnemonic() {
  wallet = await DirectSecp256k1HdWallet.generate(12, { prefix: 'dys2' })
  mnemonic.value = wallet.mnemonic
  const [acct] = await wallet.getAccounts()
  address.value = acct.address
}

async function applyMnemonic() {
  const seed = mnemonic.value.trim()
  if (!seed) { wallet = null; address.value = ''; return }
  wallet = await DirectSecp256k1HdWallet.fromMnemonic(seed, { prefix: 'dys2' })
  const [acct] = await wallet.getAccounts()
  address.value = acct.address
}

// topic ops
function shortTopic(t: string) { return t.replace(/^\/[\w-]+\/v\d+\//, '/') }
function short(s: string, n = 8) { return s.length <= 2*n ? s : `${s.slice(0,n)}…${s.slice(-n)}` }
function formatTime(ts: number) { return new Date(ts).toLocaleTimeString() }

async function joinRoom() {
  if (!client.value) return
  const name = room.value.trim()
  if (!name) return
  const topic = client.value.buildTopic('chat', name)
  await ensureSubscribed(topic)
  selectedTopic.value = topic
  room.value = ''
}

async function ensureSubscribed(topic: string) {
  if (!client.value) return
  if (topics.value.includes(topic)) return
  if (!byTopic[topic]) byTopic[topic] = []
  const handler = (msg: DysonMessage) => {
    const text = extractText(msg)
    const signer = msg.envelope?.body?.messages?.[0]?.signer || msg.from
    byTopic[topic].push({ id: `${Date.now()}-${Math.random()}`, topic, text, from: msg.from, signer, ts: Date.now() })
    if (selectedTopic.value === topic) nextTick(scrollToBottom)
  }
  await client.value.subscribe(topic, handler)
  topics.value = [...topics.value, topic]
}

async function leaveTopic(topic: string) {
  if (!client.value) return
  topics.value = topics.value.filter(t => t !== topic)
  selectedTopic.value = selectedTopic.value === topic ? '' : selectedTopic.value
  const entryHandlers = (client.value as any).topics?.get?.(topic)?.handlers // defensive; SDK manages handlers internally
  await client.value.unsubscribe(topic)
  delete byTopic[topic]
}

function selectTopic(t: string) { selectedTopic.value = t; nextTick(scrollToBottom) }

// message compose
const canSend = computed(() => !!client.value && !!selectedTopic.value && !!draft.value.trim() && !!wallet && !!address.value)
const sendDisabledReason = computed(() => {
  if (!connected.value) return 'Not connected'
  if (!client.value) return 'Client not ready'
  if (!selectedTopic.value) return 'Select or join a topic'
  if (!draft.value.trim()) return 'Message is empty'
  if (!wallet) return 'No wallet configured'
  if (!address.value) return 'Address not set'
  return ''
})
function clearDraft() { draft.value = '' }

async function send() {
  if (!client.value || !selectedTopic.value) return
  const text = draft.value.trim()
  if (!text) return
  if (!wallet || !address.value) throw new Error('Set mnemonic first')
  const signer = await createOfflineSignerSigner({ wallet, address: address.value })
  await client.value.publishJson({ root: 'chat', suffix: selectedTopic.value.split('/').pop() || '', data: { t: Date.now(), text }, signer })
  draft.value = ''
}

// extract text from validated DysonMessage
function extractText(msg: DysonMessage): string {
  const env = msg.envelope
  if (!env) return ''
  const m: any = env.body?.messages?.[0] || {}
  const data: string = typeof m.data === 'string' ? m.data : ''
  try { const j = JSON.parse(data); return typeof j?.text === 'string' ? j.text : data } catch { return data }
}

// peers → topics map
function startPeersRefresh() {
  stopPeersRefresh()
  peersTimer = setInterval(refreshPeers, 3000)
  void refreshPeers()
}
function stopPeersRefresh() { if (peersTimer) { clearInterval(peersTimer); peersTimer = null } }
async function refreshPeers() {
  if (!client.value) return
  const ps: any = (client.value.libp2p.services as any).pubsub
  const inv = new Map<string, Set<string>>()
  for (const t of topics.value) {
    const subs: any[] = ps.getSubscribers?.(t) || []
    for (const id of subs.map(x => x?.toString?.() || String(x))) {
      if (!inv.has(id)) inv.set(id, new Set())
      inv.get(id)!.add(t)
    }
  }
  peers.value = Array.from(inv.entries()).map(([id, ts]) => ({ id, topics: Array.from(ts) }))
}

function scrollToBottom() {
  const el = scrollArea.value
  if (!el) return
  try { el.scrollTo({ top: el.scrollHeight }) } catch {}
}
const scrollArea = ref<HTMLElement | null>(null)

onMounted(() => { /* defer connect; user can click Connect */ })
onUnmounted(async () => { stopPeersRefresh(); await disconnect() })
</script>
