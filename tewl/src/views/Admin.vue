<script setup lang="ts">
import { ref, watch } from "vue";
import { useWallet } from "@/composables/useWallet";
import { useScript } from "@/composables/useScript";
import { getState, getScriptAddress } from "@/lib/tewl";
import type { ProtocolState } from "@/types/tewl";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const { wallet } = useWallet();
const { setMinBond, resetAll } = useScript();
const scriptAddress = getScriptAddress();

const state = ref<ProtocolState | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const txPending = ref(false);
const newMinBond = ref("");
const confirmReset = ref(false);

const isOwner = ref(false);

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    state.value = await getState();
    newMinBond.value = state.value.min_bond;
    // Check if current wallet is the script owner
    isOwner.value = wallet.value.address === scriptAddress;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    loading.value = false;
  }
}

async function handleSetMinBond() {
  if (!newMinBond.value) return;
  txPending.value = true;
  error.value = null;
  try {
    await setMinBond(newMinBond.value);
    await loadData();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

async function handleResetAll() {
  if (!confirmReset.value) return;
  txPending.value = true;
  error.value = null;
  try {
    await resetAll();
    confirmReset.value = false;
    await loadData();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Transaction failed";
  } finally {
    txPending.value = false;
  }
}

watch(() => wallet.value.address, loadData, { immediate: true });
</script>

<template>
  <div class="max-w-2xl space-y-6">
    <h1 class="text-2xl font-bold">Admin</h1>

    <Card v-if="!wallet.address" class="p-4">Connect wallet to continue</Card>

    <div v-else-if="error" class="p-4 bg-destructive/10 text-destructive rounded-lg">
      {{ error }}
    </div>

    <div v-else-if="loading" class="text-muted-foreground">Loading...</div>

    <template v-else>
      <!-- Protocol State -->
      <Card class="p-4">
        <h2 class="text-lg font-semibold mb-3">Protocol State</h2>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-muted-foreground">Script Address:</span>
            <code class="ml-2 text-xs">{{ scriptAddress }}</code>
          </div>
          <div>
            <span class="text-muted-foreground">Next Request ID:</span>
            <span class="ml-2">{{ state?.next_request_id }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">Current Min Bond:</span>
            <span class="ml-2 font-mono">{{ state?.min_bond }} udys</span>
          </div>
          <div>
            <span class="text-muted-foreground">Active Request:</span>
            <span class="ml-2">{{ state?.active_request_id ?? "None" }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">Commit Timeout:</span>
            <span class="ml-2">{{ state?.commit_timeout_seconds ?? 30 }}s</span>
          </div>
          <div>
            <span class="text-muted-foreground">Reveal Timeout:</span>
            <span class="ml-2">{{ state?.reveal_timeout_seconds ?? 30 }}s</span>
          </div>
        </div>
      </Card>

      <!-- Set Min Bond -->
      <Card class="p-4">
        <h2 class="text-lg font-semibold mb-3">Set Minimum Bond</h2>
        
        <div v-if="!isOwner" class="p-3 bg-yellow-50 text-yellow-800 rounded text-sm mb-4">
          ⚠️ Only the script owner can change the minimum bond.
          <br />
          <span class="text-xs">Your address: {{ wallet.address }}</span>
        </div>

        <div class="space-y-4">
          <div class="space-y-2">
            <Label>New Minimum Bond (udys)</Label>
            <Input v-model="newMinBond" placeholder="100" />
            <p class="text-xs text-muted-foreground">
              Providers need at least this amount bonded to be active
            </p>
          </div>
          <Button @click="handleSetMinBond" :disabled="txPending || !newMinBond">
            {{ txPending ? "Updating..." : "Update Min Bond" }}
          </Button>
        </div>
      </Card>

      <!-- Reset All -->
      <Card class="p-4 border-destructive">
        <h2 class="text-lg font-semibold mb-3 text-destructive">Danger Zone</h2>
        
        <div v-if="!isOwner" class="p-3 bg-yellow-50 text-yellow-800 rounded text-sm mb-4">
          ⚠️ Only the script owner can reset all data.
        </div>

        <div class="space-y-4">
          <p class="text-sm text-muted-foreground">
            Delete all providers, requests, and state. This action is irreversible.
          </p>
          <label class="flex items-center gap-2 text-sm">
            <input type="checkbox" v-model="confirmReset" class="rounded" />
            I understand this will delete all data
          </label>
          <Button
            variant="destructive"
            @click="handleResetAll"
            :disabled="txPending || !confirmReset"
          >
            {{ txPending ? "Resetting..." : "Reset All Data" }}
          </Button>
        </div>
      </Card>
    </template>
  </div>
</template>

