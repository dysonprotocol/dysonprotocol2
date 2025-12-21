<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { listProviders, getState } from "@/lib/tewl";
import type { Provider, ProtocolState } from "@/types/tewl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const providers = ref<Provider[]>([]);
const state = ref<ProtocolState | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const filter = ref<"all" | "active" | "inactive">("all");

const filteredProviders = computed(() => {
  if (filter.value === "all") return providers.value;
  return providers.value.filter((p) => p.status === filter.value);
});

const stats = computed(() => ({
  total: providers.value.length,
  active: providers.value.filter((p) => p.status === "active").length,
  inactive: providers.value.filter((p) => p.status === "inactive").length,
  totalBond: providers.value.reduce((sum, p) => sum + BigInt(p.bond || "0"), 0n).toString(),
}));

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    [providers.value, state.value] = await Promise.all([listProviders(), getState()]);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load";
  } finally {
    loading.value = false;
  }
}

function formatReputation(p: Provider) {
  const total = p.reputation?.total ?? 0;
  const correct = p.reputation?.correct ?? 0;
  const slashed = p.reputation?.slashed ?? 0;
  if (total === 0) return "No history";
  const pct = ((correct / total) * 100).toFixed(0);
  return `${correct}/${total} (${pct}%)${slashed > 0 ? ` • ${slashed} slashed` : ""}`;
}

onMounted(loadData);
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Providers</h1>
      <Button variant="outline" size="sm" @click="loadData">Refresh</Button>
    </div>

    <div v-if="error" class="p-4 bg-destructive/10 text-destructive rounded-lg">
      {{ error }}
    </div>

    <div v-else-if="loading" class="text-muted-foreground">Loading...</div>

    <template v-else>
      <!-- Stats -->
      <div class="grid grid-cols-4 gap-4">
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Total Providers</div>
          <div class="text-2xl font-bold">{{ stats.total }}</div>
        </Card>
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Active</div>
          <div class="text-2xl font-bold text-green-600">{{ stats.active }}</div>
        </Card>
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Inactive</div>
          <div class="text-2xl font-bold text-yellow-600">{{ stats.inactive }}</div>
        </Card>
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Total Bonded</div>
          <div class="text-2xl font-bold">{{ stats.totalBond }} udys</div>
        </Card>
      </div>

      <!-- Min Bond Info -->
      <Card class="p-3 bg-muted/50">
        <span class="text-sm text-muted-foreground">
          Minimum bond to be active: <strong>{{ state?.min_bond || "0" }} udys</strong>
        </span>
      </Card>

      <!-- Filter -->
      <div class="flex gap-2">
        <Button
          v-for="f in ['all', 'active', 'inactive'] as const"
          :key="f"
          :variant="filter === f ? 'default' : 'outline'"
          size="sm"
          @click="filter = f"
        >
          {{ f.charAt(0).toUpperCase() + f.slice(1) }}
          ({{ f === 'all' ? stats.total : f === 'active' ? stats.active : stats.inactive }})
        </Button>
      </div>

      <!-- Provider List -->
      <div v-if="filteredProviders.length === 0" class="text-muted-foreground">
        No providers found
      </div>
      <div v-else class="space-y-3">
        <Card v-for="p in filteredProviders" :key="p.address" class="p-4">
          <div class="flex items-start justify-between">
            <div class="space-y-2">
              <div class="flex items-center gap-2">
                <code class="text-sm font-mono">{{ p.address }}</code>
                <span
                  class="px-2 py-0.5 text-xs rounded"
                  :class="p.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'"
                >
                  {{ p.status }}
                </span>
              </div>
              <div class="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span class="text-muted-foreground">Bond:</span>
                  <span class="ml-2 font-mono">{{ p.bond }} udys</span>
                </div>
                <div>
                  <span class="text-muted-foreground">Reputation:</span>
                  <span class="ml-2">{{ formatReputation(p) }}</span>
                </div>
                <div>
                  <span class="text-muted-foreground">Registered:</span>
                  <span class="ml-2">Block #{{ p.registered_at }}</span>
                </div>
              </div>
            </div>
            <div class="text-right">
              <div
                v-if="p.reputation && p.reputation.total > 0"
                class="text-2xl font-bold"
                :class="{
                  'text-green-600': (p.reputation.correct / p.reputation.total) >= 0.8,
                  'text-yellow-600': (p.reputation.correct / p.reputation.total) >= 0.5 && (p.reputation.correct / p.reputation.total) < 0.8,
                  'text-red-600': (p.reputation.correct / p.reputation.total) < 0.5,
                }"
              >
                {{ ((p.reputation.correct / p.reputation.total) * 100).toFixed(0) }}%
              </div>
              <div v-else class="text-sm text-muted-foreground">New</div>
            </div>
          </div>
        </Card>
      </div>
    </template>
  </div>
</template>

