<script setup lang="ts">
import { useTxLog } from '@/composables/useTxLog'

const { recentTxs, clearLog } = useTxLog()

const explorerBaseUrl = import.meta.env.VITE_TX_EXPLORER_URL || 'http://localhost:5173/txs'

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function truncateHash(hash?: string): string {
  if (!hash) return '—'
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'success': return 'text-green-500'
    case 'failed': return 'text-red-500'
    case 'pending': return 'text-yellow-500 animate-pulse'
    default: return 'text-muted-foreground'
  }
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'success': return '✓'
    case 'failed': return '✗'
    case 'pending': return '⏳'
    default: return '?'
  }
}
</script>

<template>
  <div class="bg-card border border-border rounded-lg p-3 text-sm">
    <div class="flex items-center justify-between mb-2">
      <h3 class="font-semibold text-foreground">Transaction Log</h3>
      <button
        v-if="recentTxs.length > 0"
        class="text-xs text-muted-foreground hover:text-foreground"
        @click="clearLog"
      >
        Clear
      </button>
    </div>

    <div v-if="recentTxs.length === 0" class="text-muted-foreground text-center py-4">
      No transactions yet
    </div>

    <div v-else class="space-y-2 max-h-64 overflow-y-auto">
      <div
        v-for="tx in recentTxs"
        :key="tx.id"
        class="bg-secondary/30 rounded p-2 font-mono text-xs"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-muted-foreground">{{ formatTime(tx.timestamp) }}</span>
          <span class="font-semibold text-foreground">{{ tx.functionName }}</span>
          <span :class="getStatusColor(tx.status)" class="font-bold">
            {{ getStatusIcon(tx.status) }} {{ tx.status }}
          </span>
        </div>

        <div v-if="tx.txHash" class="mt-1 text-muted-foreground">
          <span class="opacity-60">Hash:</span>
          <a
            :href="`${explorerBaseUrl}/${tx.txHash}`"
            target="_blank"
            class="text-primary hover:underline ml-1"
          >
            {{ truncateHash(tx.txHash) }}
          </a>
        </div>

        <div v-if="tx.gasUsed" class="text-muted-foreground">
          <span class="opacity-60">Gas:</span> {{ tx.gasUsed }} / {{ tx.gasWanted }}
        </div>

        <div v-if="tx.error" class="mt-1 text-red-400 break-all">
          {{ tx.error }}
        </div>

        <div v-if="tx.rawLog && tx.status === 'failed'" class="mt-1 text-red-400 break-all text-[10px]">
          {{ tx.rawLog }}
        </div>

        <details v-if="tx.result" class="mt-1">
          <summary class="text-muted-foreground cursor-pointer hover:text-foreground">
            Result
          </summary>
          <pre class="mt-1 text-[10px] bg-black/20 p-1 rounded overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify(tx.result, null, 2) }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>

