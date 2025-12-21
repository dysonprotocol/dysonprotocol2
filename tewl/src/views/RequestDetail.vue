<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { useWallet } from "@/composables/useWallet";
import { useScript } from "@/composables/useScript";
import { getRequest, getEffectiveStatus } from "@/lib/tewl";
import type { Request } from "@/types/tewl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const route = useRoute();
const { wallet } = useWallet();
const { finalize } = useScript();

const request = ref<Request | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const txPending = ref(false);

// Collapsible sections
const showSchema = ref(false);
const showScorer = ref(false);
const showRawCommits = ref(false);

const requestId = computed(() => parseInt(route.params.id as string));

// Live time for deadline tracking
const now = ref(new Date());
setInterval(() => { now.value = new Date(); }, 1000);

const commitDeadline = computed(() => request.value?.commit_deadline ? new Date(request.value.commit_deadline) : null);
const revealDeadline = computed(() => request.value?.reveal_deadline ? new Date(request.value.reveal_deadline) : null);
const commitPassed = computed(() => commitDeadline.value && now.value >= commitDeadline.value);
const revealPassed = computed(() => revealDeadline.value && now.value >= revealDeadline.value);

const effectiveStatus = computed(() => request.value ? getEffectiveStatus(request.value) : "");
const canFinalize = computed(() => effectiveStatus.value === "finalizing");
const isTerminal = computed(() => ["resolved", "failed"].includes(effectiveStatus.value));

// Merged provider participation data
const providers = computed(() => {
  if (!request.value) return [];
  const commits = request.value.commits || {};
  const reveals = request.value.reveals || {};
  const scores = request.value.scores || {};
  const allProviders = new Set([...Object.keys(commits), ...Object.keys(reveals)]);
  return Array.from(allProviders).map(addr => ({
    address: addr,
    committed: addr in commits,
    revealed: addr in reveals,
    response: reveals[addr]?.response,
    score: scores[addr],
  }));
});

function truncate(addr: string) {
  if (!addr || addr.length < 20) return addr;
  return `${addr.slice(0, 8)}...${addr.slice(-6)}`;
}

async function copy(text: string) {
  await navigator.clipboard.writeText(text);
}

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    request.value = await getRequest(requestId.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    loading.value = false;
  }
}

async function handleFinalize() {
  txPending.value = true;
  error.value = null;
  try {
    await finalize(requestId.value);
    await loadData();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="space-y-4 max-w-4xl">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <h1 class="text-xl font-bold">Request #{{ requestId }}</h1>
        <span 
          class="px-2 py-0.5 text-xs font-medium rounded-full"
          :class="{
            'bg-yellow-100 text-yellow-800': effectiveStatus === 'pending',
            'bg-blue-100 text-blue-800': effectiveStatus === 'active',
            'bg-purple-100 text-purple-800': effectiveStatus === 'revealing',
            'bg-orange-100 text-orange-800': effectiveStatus === 'finalizing',
            'bg-green-100 text-green-800': effectiveStatus === 'resolved',
            'bg-red-100 text-red-800': effectiveStatus === 'failed',
          }"
        >
          {{ effectiveStatus }}
        </span>
        <span class="text-sm text-muted-foreground">{{ request?.fee }} udys</span>
      </div>
      <div class="flex gap-2">
        <Button v-if="canFinalize" size="sm" @click="handleFinalize" :disabled="txPending || !wallet.address">
          {{ txPending ? "Finalizing..." : "Finalize" }}
        </Button>
        <Button variant="outline" size="sm" @click="loadData">↻</Button>
      </div>
    </div>

    <div v-if="error" class="p-3 bg-destructive/10 text-destructive rounded text-sm">
      {{ error }}
    </div>

    <div v-else-if="loading" class="text-muted-foreground">Loading...</div>

    <div v-else-if="!request" class="text-muted-foreground">Request not found</div>

    <template v-else>
      <!-- Prompt (always visible, prominent) -->
      <Card class="p-4">
        <p class="text-lg">"{{ request.prompt }}"</p>
        <div class="mt-2 flex gap-4 text-xs text-muted-foreground">
          <span @click="copy(request.requester)" class="cursor-pointer hover:text-foreground">
            by {{ truncate(request.requester) }}
          </span>
          <span v-if="commitDeadline" :class="{ 'text-red-500': commitPassed }">
            commit: {{ commitDeadline.toLocaleTimeString() }}{{ commitPassed ? ' ✓' : '' }}
          </span>
          <span v-if="revealDeadline" :class="{ 'text-red-500': revealPassed }">
            reveal: {{ revealDeadline.toLocaleTimeString() }}{{ revealPassed ? ' ✓' : '' }}
          </span>
        </div>
      </Card>

      <!-- Two column layout for terminal states -->
      <div :class="isTerminal ? 'grid md:grid-cols-2 gap-4' : 'space-y-4'">
        <!-- Result (hero for resolved) -->
        <Card v-if="request.result" class="p-4 bg-green-50 border-green-200">
          <h2 class="text-sm font-semibold text-green-700 mb-2">Result</h2>
          <pre class="text-sm font-mono">{{ JSON.stringify(request.result, null, 2) }}</pre>
        </Card>

        <Card v-else-if="effectiveStatus === 'failed'" class="p-4 bg-red-50 border-red-200">
          <h2 class="text-sm font-semibold text-red-700">No Consensus</h2>
          <p class="text-sm text-red-600 mt-1">Request failed - fee refunded to requester</p>
        </Card>

        <!-- Provider Participation -->
        <Card class="p-4">
          <h2 class="text-sm font-semibold mb-3">
            Providers ({{ providers.length }})
          </h2>
          <div v-if="providers.length === 0" class="text-sm text-muted-foreground">
            No participation yet
          </div>
          <div v-else class="space-y-2">
            <div 
              v-for="p in providers" 
              :key="p.address"
              class="flex items-center justify-between text-sm border-b border-muted pb-2 last:border-0"
            >
              <div class="flex items-center gap-2">
                <code 
                  class="text-xs cursor-pointer hover:text-primary" 
                  @click="copy(p.address)"
                  :title="p.address"
                >
                  {{ truncate(p.address) }}
                </code>
                <span class="text-xs">
                  <span :class="p.committed ? 'text-green-600' : 'text-muted-foreground'">
                    {{ p.committed ? '✓' : '○' }} commit
                  </span>
                  <span class="mx-1">→</span>
                  <span :class="p.revealed ? 'text-green-600' : 'text-muted-foreground'">
                    {{ p.revealed ? '✓' : '○' }} reveal
                  </span>
                </span>
              </div>
              <span 
                v-if="p.score !== undefined"
                class="px-2 py-0.5 text-xs rounded"
                :class="{
                  'bg-green-100 text-green-800': p.score > 0,
                  'bg-red-100 text-red-800': p.score <= 0,
                }"
              >
                {{ typeof p.score === 'number' ? p.score.toFixed(2) : p.score }}
              </span>
            </div>
          </div>
        </Card>
      </div>

      <!-- Collapsible details -->
      <div class="flex flex-wrap gap-2 text-sm">
        <button 
          @click="showSchema = !showSchema"
          class="px-3 py-1 rounded border hover:bg-muted transition-colors"
        >
          {{ showSchema ? '▾' : '▸' }} Schema
        </button>
        <button 
          v-if="request.scorer"
          @click="showScorer = !showScorer"
          class="px-3 py-1 rounded border hover:bg-muted transition-colors"
        >
          {{ showScorer ? '▾' : '▸' }} Scorer
        </button>
        <button 
          @click="showRawCommits = !showRawCommits"
          class="px-3 py-1 rounded border hover:bg-muted transition-colors"
        >
          {{ showRawCommits ? '▾' : '▸' }} Raw Data
        </button>
      </div>

      <!-- Schema (collapsible) -->
      <Card v-if="showSchema" class="p-4">
        <h2 class="text-sm font-semibold mb-2">Response Schema</h2>
        <pre class="p-2 bg-muted rounded text-xs overflow-auto">{{ JSON.stringify(request.response_schema, null, 2) }}</pre>
      </Card>

      <!-- Scorer (collapsible) -->
      <Card v-if="showScorer && request.scorer" class="p-4">
        <h2 class="text-sm font-semibold mb-2">Scorer</h2>
        <pre class="p-2 bg-muted rounded text-xs overflow-auto whitespace-pre-wrap">{{ request.scorer }}</pre>
      </Card>

      <!-- Raw commits/reveals (collapsible) -->
      <Card v-if="showRawCommits" class="p-4">
        <h2 class="text-sm font-semibold mb-2">Raw Commits & Reveals</h2>
        <div class="grid md:grid-cols-2 gap-4">
          <div>
            <h3 class="text-xs font-medium text-muted-foreground mb-1">Commits</h3>
            <pre class="p-2 bg-muted rounded text-xs overflow-auto max-h-48">{{ JSON.stringify(request.commits, null, 2) }}</pre>
          </div>
          <div>
            <h3 class="text-xs font-medium text-muted-foreground mb-1">Reveals</h3>
            <pre class="p-2 bg-muted rounded text-xs overflow-auto max-h-48">{{ JSON.stringify(request.reveals, null, 2) }}</pre>
          </div>
        </div>
      </Card>
    </template>
  </div>
</template>
