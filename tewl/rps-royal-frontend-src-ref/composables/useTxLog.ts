import { ref, computed } from 'vue'

export interface TxLogEntry {
  id: string
  timestamp: Date
  functionName: string
  status: 'pending' | 'success' | 'failed'
  txHash?: string
  gasUsed?: string
  gasWanted?: string
  error?: string
  rawLog?: string
  result?: any
}

const txLog = ref<TxLogEntry[]>([])
const maxEntries = 20

export function useTxLog() {
  function addTx(entry: Omit<TxLogEntry, 'id' | 'timestamp'>): string {
    const id = crypto.randomUUID()
    const newEntry: TxLogEntry = {
      ...entry,
      id,
      timestamp: new Date(),
    }
    console.log('[TxLog] Adding tx:', newEntry)
    txLog.value = [newEntry, ...txLog.value].slice(0, maxEntries)
    return id
  }

  function updateTx(id: string, updates: Partial<TxLogEntry>) {
    console.log('[TxLog] Updating tx:', id, updates)
    const idx = txLog.value.findIndex(t => t.id === id)
    if (idx !== -1) {
      txLog.value[idx] = { ...txLog.value[idx], ...updates }
      // Trigger reactivity
      txLog.value = [...txLog.value]
    }
  }

  function clearLog() {
    txLog.value = []
  }

  const recentTxs = computed(() => txLog.value.slice(0, 10))

  return {
    txLog,
    recentTxs,
    addTx,
    updateTx,
    clearLog,
  }
}

