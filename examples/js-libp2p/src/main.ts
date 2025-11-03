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

const connectBtn = document.getElementById('connect') as HTMLButtonElement
const statusEl = document.getElementById('status') as HTMLElement
const payloadEl = document.getElementById('payload') as HTMLTextAreaElement
const topicSuffixEl = document.getElementById('topicSuffix') as HTMLInputElement
const publishCosmjsBtn = document.getElementById('publishCosmjs') as HTMLButtonElement
const publishKeplrBtn = document.getElementById('publishKeplr') as HTMLButtonElement
const messagesEl = document.getElementById('messages') as HTMLElement
const debugEl = document.getElementById('debug') as HTMLElement
const mnemonicInput = document.getElementById('mnemonic') as HTMLTextAreaElement
const generateMnemonicBtn = document.getElementById('generateMnemonic') as HTMLButtonElement
const useMnemonicBtn = document.getElementById('useMnemonic') as HTMLButtonElement
const cosmjsAddressEl = document.getElementById('cosmjsAddress') as HTMLElement
const keplrAddressEl = document.getElementById('keplrAddress') as HTMLElement

const DEFAULT_PREFIX = 'dys2'

let client: DysonClient | undefined
let keplrAvailable = typeof window.keplr !== 'undefined'
let keplrAddress = ''
let cosmjsWallet: DirectSecp256k1HdWallet | undefined
let cosmjsAddress = ''
const subscribedTopics = new Map<string, DysonMessageHandler>()

type DysonMessageHandler = (msg: DysonMessage) => void

function appendMessage(text: string) {
    const div = document.createElement('div')
    div.textContent = text
    messagesEl.prepend(div)
}

function updateDebug(info: unknown) {
    debugEl.textContent = JSON.stringify(info, null, 2)
}

function logLine(message: string, extra?: unknown) {
    const ts = new Date().toISOString()
    const line = extra !== undefined ? `${ts} ${message} ${JSON.stringify(extra)}` : `${ts} ${message}`
    console.log('[dyson-demo]', message, extra ?? '')
    debugEl.textContent = `${line}\n${debugEl.textContent || ''}`.slice(0, 8000)
}

function updateButtons() {
    const hasClient = !!client
    const hasCosmjs = !!(cosmjsWallet && cosmjsAddress)
    publishCosmjsBtn.disabled = !(hasClient && hasCosmjs)
    publishCosmjsBtn.title = hasCosmjs
        ? hasClient
            ? ''
            : 'Connect before publishing'
        : 'Generate or paste a mnemonic first'

    const hasKeplrSigner = hasClient && keplrAvailable
    publishKeplrBtn.disabled = !hasKeplrSigner
    publishKeplrBtn.title = keplrAvailable
        ? hasClient
            ? ''
            : 'Connect before publishing'
        : 'Keplr extension not detected'
}

function renderAddresses() {
    cosmjsAddressEl.textContent = cosmjsAddress || '—'
    if (!keplrAvailable) {
        keplrAddressEl.textContent = 'Keplr not detected'
    } else {
        keplrAddressEl.textContent = keplrAddress || '—'
    }
    updateButtons()
}

async function connectDyson() {
    statusEl.textContent = 'Connecting…'
    client = await createDysonClient()
    statusEl.textContent = `Connected as ${client.peerId}`
    logLine('bootstrap', client.bootstrap)
    logLine('peerId', client.peerId)
    logLine('topicPrefix', client.topicPrefix)
    keplrAvailable = typeof window.keplr !== 'undefined'
    keplrAddress = ''
    subscribedTopics.clear()
    renderAddresses()

    // libp2p event logs
    try {
        client.libp2p.addEventListener('peer:connect', (e: any) => logLine('peer:connect', { id: e?.detail?.remotePeer?.toString?.() }))
        client.libp2p.addEventListener('peer:disconnect', (e: any) => logLine('peer:disconnect', { id: e?.detail?.remotePeer?.toString?.() }))
        client.libp2p.addEventListener('peer:discovery', (e: any) => logLine('peer:discovery', { id: e?.detail?.id?.toString?.(), addrs: e?.detail?.multiaddrs?.map?.((m: any) => m?.toString?.()) }))
            ; (client.libp2p.services as any)?.pubsub?.addEventListener?.('message', (evt: any) => {
                const d = evt?.detail
                logLine('pubsub:message', { topic: d?.topic, from: d?.from })
            })
    } catch (err) {
        logLine('event hooks error', (err as Error).message)
    }
}

function buildTopic(address: string) {
    if (!client) throw new Error('Not connected')
    const suffix = topicSuffixEl.value.trim() || 'demo'
    return client.buildTopic(address, suffix)
}

async function ensureSubscription(topic: string) {
    if (!client) return
    if (subscribedTopics.has(topic)) return
    logLine('subscribe()', { topic })
    const handler: DysonMessageHandler = (msg) => {
        const payloadText = msg.payloadJson !== undefined ? JSON.stringify(msg.payloadJson) : uint8ToString(msg.payload)
        logLine('RX', { topic: msg.topic, from: msg.from })
        appendMessage(`RX ${msg.from}: ${payloadText}`)
    }
    await client.subscribe(topic, handler)
    subscribedTopics.set(topic, handler)
    appendMessage(`Subscribed to ${topic}`)
}

async function ensureCosmjsWallet(mnemonic: string) {
    const trimmed = mnemonic.trim()
    if (!trimmed) {
        cosmjsWallet = undefined
        cosmjsAddress = ''
        renderAddresses()
        return
    }
    cosmjsWallet = await DirectSecp256k1HdWallet.fromMnemonic(trimmed, { prefix: DEFAULT_PREFIX })
    const [account] = await cosmjsWallet.getAccounts()
    cosmjsAddress = account.address
    renderAddresses()
    if (client && cosmjsAddress) {
        const topic = buildTopic(cosmjsAddress)
        logLine('auto-subscribe after seed', { topic })
        await ensureSubscription(topic)
    }
}

async function generateMnemonic() {
    const wallet = await DirectSecp256k1HdWallet.generate(12, { prefix: DEFAULT_PREFIX })
    mnemonicInput.value = wallet.mnemonic
    cosmjsWallet = wallet
    const [account] = await wallet.getAccounts()
    cosmjsAddress = account.address
    renderAddresses()
}

async function publishWithCosmjs() {
    if (!client) throw new Error('Not connected')
    if (!cosmjsWallet) throw new Error('Set a CosmJS seed first')
    const signer = await createOfflineSignerSigner({ wallet: cosmjsWallet, address: cosmjsAddress || undefined })
    cosmjsAddress = signer.address
    renderAddresses()
    const topic = buildTopic(cosmjsAddress)
    await ensureSubscription(topic)
    const payloadJson = payloadEl.value.trim() || '{}'
    const payloadBytes = uint8FromString(payloadJson)
    logLine('publish()', { topic, bytes: payloadBytes.length })
    await client.publish({ topic, payload: payloadBytes, signer })
    appendMessage(`TX ${topic}: ${payloadJson}`)
}

async function publishWithKeplr() {
    if (!client) throw new Error('Not connected')
    const signer = await createKeplrSigner(client.chainId)
    keplrAddress = signer.address
    renderAddresses()
    const topic = buildTopic(keplrAddress)
    await ensureSubscription(topic)
    const payloadJson = payloadEl.value.trim() || '{}'
    const payloadBytes = uint8FromString(payloadJson)
    logLine('publish()', { topic, bytes: payloadBytes.length })
    await client.publish({ topic, payload: payloadBytes, signer })
    appendMessage(`TX ${topic}: ${payloadJson}`)
}

connectBtn?.addEventListener('click', async () => {
    connectBtn.disabled = true
    try {
        await connectDyson()
    } catch (err) {
        statusEl.textContent = `Error: ${(err as Error).message}`
        console.error(err)
        connectBtn.disabled = false
    }
})

publishCosmjsBtn?.addEventListener('click', async () => {
    publishCosmjsBtn.disabled = true
    try {
        await publishWithCosmjs()
    } catch (err) {
        appendMessage(`CosmJS publish error: ${(err as Error).message}`)
        console.error(err)
    } finally {
        publishCosmjsBtn.disabled = false
    }
})

publishKeplrBtn?.addEventListener('click', async () => {
    publishKeplrBtn.disabled = true
    try {
        await publishWithKeplr()
    } catch (err) {
        appendMessage(`Keplr publish error: ${(err as Error).message}`)
        console.error(err)
    } finally {
        publishKeplrBtn.disabled = false
    }
})

generateMnemonicBtn?.addEventListener('click', async () => {
    await generateMnemonic()
})

useMnemonicBtn?.addEventListener('click', async () => {
    await ensureCosmjsWallet(mnemonicInput.value)
})

renderAddresses()
updateButtons()

    // Auto-connect on page load
    ; (async () => {
        try {
            await connectDyson()
            await ensureCosmjsWallet(mnemonicInput.value)
        } catch (err) {
            console.error('Auto-connect failed', err)
        }
    })()

