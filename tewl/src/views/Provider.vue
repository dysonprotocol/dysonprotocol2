<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useWallet } from "@/composables/useWallet";
import { useScript } from "@/composables/useScript";
import { getProvider, getActiveRequest, computeCommitHash, generateSalt, getState, getEffectiveStatus } from "@/lib/tewl";
import type { Provider, Request } from "@/types/tewl";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const { wallet } = useWallet();
const { depositBond, withdrawBond, commit, reveal, finalize } = useScript();

const provider = ref<Provider | null>(null);
const activeRequest = ref<Request | null>(null);
const minBond = ref("0");
const loading = ref(true);
const error = ref<string | null>(null);
const formError = ref<string | null>(null); // Error shown below the form
const txPending = ref(false);

// Bond form
const depositAmount = ref("");
const withdrawAmount = ref("");

// Commit/Reveal form
const responseJson = ref("");
const salt = ref(generateSalt());

const effectiveStatus = computed(() =>
  activeRequest.value ? getEffectiveStatus(activeRequest.value) : ""
);

const commitHash = computed(() => {
  if (!activeRequest.value || !responseJson.value || !wallet.value.address) return "";
  try {
    const parsed = JSON.parse(responseJson.value);
    return computeCommitHash(activeRequest.value.request_id, parsed, salt.value, wallet.value.address);
  } catch {
    return "";
  }
});

const hasCommitted = computed(() =>
  activeRequest.value && wallet.value.address
    ? !!activeRequest.value.commits?.[wallet.value.address]
    : false
);

const hasRevealed = computed(() =>
  activeRequest.value && wallet.value.address
    ? !!activeRequest.value.reveals?.[wallet.value.address]
    : false
);

// Get the stored commit hash for verification
const storedCommitHash = computed(() => {
  if (!activeRequest.value || !wallet.value.address) return null;
  return activeRequest.value.commits?.[wallet.value.address]?.hash ?? null;
});

// Check if current form data matches stored commit
const hashMatches = computed(() => {
  if (!storedCommitHash.value || !commitHash.value) return null;
  return commitHash.value === storedCommitHash.value;
});

async function loadData() {
  if (!wallet.value.address) return;
  loading.value = true;
  error.value = null;

  try {
    const [providerData, requestData, stateData] = await Promise.all([
      getProvider(wallet.value.address),
      getActiveRequest(),
      getState(),
    ]);
    provider.value = providerData;
    activeRequest.value = requestData;
    minBond.value = stateData.min_bond;

    // Auto-load saved response if user has committed
    if (requestData && wallet.value.address && requestData.commits?.[wallet.value.address]) {
      loadSavedResponse();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    loading.value = false;
  }
}

async function handleDeposit() {
  if (!depositAmount.value) return;
  txPending.value = true;
  error.value = null;
  try {
    await depositBond(depositAmount.value);
    depositAmount.value = "";
    await loadData();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

async function handleWithdraw() {
  if (!withdrawAmount.value) return;
  txPending.value = true;
  error.value = null;
  try {
    await withdrawBond(withdrawAmount.value);
    withdrawAmount.value = "";
    await loadData();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

async function handleCommit() {
  if (!activeRequest.value || !commitHash.value) return;
  txPending.value = true;
  error.value = null;
  formError.value = null;
  try {
    await commit(activeRequest.value.request_id, commitHash.value);
    // Save BEFORE reloading data so it persists
    localStorage.setItem(`tewl_salt_${activeRequest.value.request_id}`, salt.value);
    localStorage.setItem(`tewl_response_${activeRequest.value.request_id}`, responseJson.value);
    await loadData();
  } catch (e) {
    formError.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

async function handleReveal() {
  if (!activeRequest.value) return;
  
  // Pre-check: verify hash matches before sending tx
  if (hashMatches.value === false) {
    formError.value = `Hash mismatch! Your current response/salt doesn't match your commit. Click "load saved" to restore your original data.`;
    return;
  }

  txPending.value = true;
  error.value = null;
  formError.value = null;
  try {
    const parsed = JSON.parse(responseJson.value);
    await reveal(activeRequest.value.request_id, parsed, salt.value);
    await loadData();
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Transaction failed";
    // Parse hash mismatch errors for better UX
    if (msg.includes("hash mismatch")) {
      formError.value = `Hash mismatch! The response/salt you're revealing doesn't match your commit. Click "load saved" to restore your original committed data.`;
    } else {
      formError.value = msg;
    }
  } finally {
    txPending.value = false;
  }
}

async function handleFinalize() {
  if (!activeRequest.value) return;
  txPending.value = true;
  error.value = null;
  formError.value = null;
  try {
    await finalize(activeRequest.value.request_id);
    await loadData();
  } catch (e) {
    formError.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

function loadSavedResponse() {
  if (!activeRequest.value) return;
  const savedSalt = localStorage.getItem(`tewl_salt_${activeRequest.value.request_id}`);
  const savedResponse = localStorage.getItem(`tewl_response_${activeRequest.value.request_id}`);
  if (savedSalt) salt.value = savedSalt;
  if (savedResponse) responseJson.value = savedResponse;
  formError.value = null; // Clear any hash mismatch error
}

watch(() => wallet.value.address, loadData, { immediate: true });
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Provider</h1>
      <Button variant="outline" size="sm" @click="loadData" :disabled="loading">Refresh</Button>
    </div>

    <Card v-if="!wallet.address" class="p-4">Connect wallet to continue</Card>

    <div v-else-if="error" class="p-4 bg-destructive/10 text-destructive rounded-lg">
      {{ error }}
    </div>

    <div v-else-if="loading" class="text-muted-foreground">Loading...</div>

    <template v-else>
      <!-- Provider Status -->
      <Card class="p-4">
        <h2 class="text-lg font-semibold mb-3">Your Status</h2>
        <div v-if="!provider" class="text-muted-foreground">
          Not registered as provider. Deposit bond to register.
        </div>
        <div v-else class="space-y-3">
          <div class="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span class="text-muted-foreground">Bond:</span>
              <span class="ml-2 font-mono">{{ provider.bond }} udys</span>
            </div>
            <div>
              <span class="text-muted-foreground">Reputation:</span>
              <span class="ml-2">{{ provider.reputation?.total ?? 0 }} ({{ provider.reputation?.correct ?? 0 }} correct)</span>
            </div>
            <div>
              <span class="text-muted-foreground">Status:</span>
              <span class="ml-2 px-2 py-0.5 rounded" :class="provider.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'">
                {{ provider.status }}
              </span>
            </div>
          </div>
          <div v-if="provider.status === 'inactive'" class="text-sm text-muted-foreground bg-muted p-2 rounded">
            ⚠️ You need at least <strong>{{ minBond }} udys</strong> bond to become active. 
          </div>
        </div>
      </Card>

      <!-- Bond Management -->
      <Card class="p-4">
        <h2 class="text-lg font-semibold mb-3">Bond Management</h2>
        <div class="flex gap-4">
          <div class="flex-1 space-y-2">
            <Label>Deposit (udys)</Label>
            <div class="flex gap-2">
              <Input v-model="depositAmount" placeholder="1000000" class="flex-1" />
              <Button @click="handleDeposit" :disabled="txPending || !depositAmount">Deposit</Button>
            </div>
          </div>
          <div class="flex-1 space-y-2">
            <Label>Withdraw (udys)</Label>
            <div class="flex gap-2">
              <Input v-model="withdrawAmount" placeholder="500000" class="flex-1" />
              <Button variant="outline" @click="handleWithdraw" :disabled="txPending || !withdrawAmount">Withdraw</Button>
            </div>
          </div>
        </div>
      </Card>

      <!-- Active Request -->
      <Card v-if="activeRequest" class="p-4">
        <h2 class="text-lg font-semibold mb-3">
          Request #{{ activeRequest.request_id }}
          <span class="ml-2 px-2 py-0.5 text-sm rounded" :class="{
            'bg-blue-100 text-blue-800': effectiveStatus === 'active',
            'bg-yellow-100 text-yellow-800': effectiveStatus === 'revealing',
            'bg-purple-100 text-purple-800': effectiveStatus === 'finalizing',
          }">{{ effectiveStatus }}</span>
        </h2>

        <div class="mb-4 p-3 bg-muted rounded text-sm space-y-1">
          <div><strong>Prompt:</strong> {{ activeRequest.prompt }}</div>
          <div><strong>Schema:</strong> <code class="text-xs">{{ JSON.stringify(activeRequest.response_schema) }}</code></div>
          <div class="pt-2 text-xs text-muted-foreground">
            Commit: {{ activeRequest.commit_deadline ? new Date(activeRequest.commit_deadline).toLocaleTimeString() : 'N/A' }} |
            Reveal: {{ activeRequest.reveal_deadline ? new Date(activeRequest.reveal_deadline).toLocaleTimeString() : 'N/A' }}
          </div>
        </div>

        <div class="space-y-4">
          <div class="space-y-2">
            <Label>Response (JSON)</Label>
            <Textarea v-model="responseJson" rows="3" placeholder='{"answer": "your response"}' class="font-mono text-sm" />
          </div>

          <div class="space-y-2">
            <Label>
              Salt
              <button @click="salt = generateSalt()" class="ml-2 text-primary hover:underline text-xs" :disabled="hasCommitted">regenerate</button>
              <button v-if="hasCommitted" @click="loadSavedResponse" class="ml-2 text-primary hover:underline text-xs font-semibold">load saved ⟲</button>
            </Label>
            <Input v-model="salt" class="font-mono text-sm" :disabled="hasCommitted && effectiveStatus === 'revealing'" />
          </div>

          <div v-if="commitHash" class="text-xs space-y-1">
            <Label>Commit Hash</Label>
            <code class="block p-2 bg-muted rounded break-all mt-1">{{ commitHash }}</code>
            
            <!-- Hash match indicator for revealing phase -->
            <div v-if="hasCommitted && storedCommitHash" class="mt-2">
              <span v-if="hashMatches === true" class="text-green-600 text-sm">
                ✓ Hash matches your commit
              </span>
              <span v-else-if="hashMatches === false" class="text-red-600 text-sm">
                ✗ Hash does NOT match your commit! Click "load saved" to restore.
              </span>
            </div>
          </div>

          <!-- Form Error (shown below form) -->
          <div v-if="formError" class="p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
            {{ formError }}
          </div>

          <div class="flex gap-2 flex-wrap">
            <Button 
              v-if="effectiveStatus === 'active' && !hasCommitted" 
              @click="handleCommit" 
              :disabled="txPending || !commitHash"
            >
              Submit Commit
            </Button>
            <span v-else-if="hasCommitted && effectiveStatus === 'active'" class="text-sm text-green-600 self-center">
              ✓ Committed
            </span>

            <Button 
              v-if="effectiveStatus === 'revealing' && hasCommitted && !hasRevealed" 
              @click="handleReveal" 
              :disabled="txPending || !responseJson || !salt || hashMatches === false"
              :class="{ 'opacity-50': hashMatches === false }"
            >
              Submit Reveal
            </Button>
            <span v-else-if="hasRevealed" class="text-sm text-green-600 self-center">
              ✓ Revealed
            </span>

            <Button 
              v-if="effectiveStatus === 'finalizing'" 
              @click="handleFinalize" 
              :disabled="txPending"
            >
              Finalize
              </Button>
          </div>
        </div>
      </Card>

      <Card v-else class="p-4 text-muted-foreground">No active request</Card>
    </template>
  </div>
</template>
