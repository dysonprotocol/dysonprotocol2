<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { getState, getActiveRequest, listRequests, listProviders, getPendingRequests, getEffectiveStatus } from "@/lib/tewl";
import type { ProtocolState, Request, Provider } from "@/types/tewl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const state = ref<ProtocolState | null>(null);
const activeRequest = ref<Request | null>(null);
const requests = ref<Request[]>([]);
const providers = ref<Provider[]>([]);
const pendingRequests = ref<Request[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const statusFilter = ref<string>("all");

const filteredRequests = computed(() => {
  if (statusFilter.value === "all") return requests.value;
  return requests.value.filter((r) => getEffectiveStatus(r) === statusFilter.value);
});

const statusCounts = computed(() => {
  const counts: Record<string, number> = { all: requests.value.length };
  for (const r of requests.value) {
    const status = getEffectiveStatus(r);
    counts[status] = (counts[status] || 0) + 1;
  }
  return counts;
});

async function loadData() {
  loading.value = true;
  error.value = null;

  try {
    [state.value, activeRequest.value, requests.value, providers.value, pendingRequests.value] = await Promise.all([
      getState(),
      getActiveRequest(),
      listRequests(),
      listProviders(),
      getPendingRequests(),
    ]);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load data";
  } finally {
    loading.value = false;
  }
}

const activeProviders = () => providers.value.filter(p => p.status === "active");

onMounted(loadData);
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Dashboard</h1>
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
          <div class="text-sm text-muted-foreground">Total Requests</div>
          <div class="text-2xl font-bold">{{ state?.next_request_id ? state.next_request_id - 1 : 0 }}</div>
        </Card>
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Active Providers</div>
          <div class="text-2xl font-bold">{{ activeProviders().length }}</div>
        </Card>
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Min Bond</div>
          <div class="text-2xl font-bold">{{ state?.min_bond || "0" }} udys</div>
        </Card>
        <Card class="p-4">
          <div class="text-sm text-muted-foreground">Queue</div>
          <div class="text-2xl font-bold">{{ pendingRequests.length }}</div>
        </Card>
      </div>

      <!-- Active Request -->
      <Card v-if="activeRequest" class="p-4">
        <h2 class="text-lg font-semibold mb-3">Active Request #{{ activeRequest.request_id }}</h2>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-muted-foreground">Status:</span>
            <span 
              class="ml-2 px-2 py-0.5 rounded"
              :class="{
                'bg-blue-100 text-blue-800': getEffectiveStatus(activeRequest) === 'active',
                'bg-purple-100 text-purple-800': getEffectiveStatus(activeRequest) === 'revealing',
                'bg-orange-100 text-orange-800': getEffectiveStatus(activeRequest) === 'finalizing',
              }"
            >
              {{ getEffectiveStatus(activeRequest) }}
            </span>
          </div>
          <div>
            <span class="text-muted-foreground">Fee:</span>
            <span class="ml-2">{{ activeRequest.fee }} udys</span>
          </div>
          <div class="col-span-2">
            <span class="text-muted-foreground">Prompt:</span>
            <span class="ml-2">{{ activeRequest.prompt }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">Commits:</span>
            <span class="ml-2">{{ Object.keys(activeRequest.commits || {}).length }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">Reveals:</span>
            <span class="ml-2">{{ Object.keys(activeRequest.reveals || {}).length }}</span>
          </div>
        </div>
        <router-link :to="`/request/${activeRequest.request_id}`" class="inline-block mt-3 text-sm text-primary hover:underline">
          View Details →
        </router-link>
      </Card>

      <!-- Pending Queue -->
      <div v-if="pendingRequests.length > 0">
        <h2 class="text-lg font-semibold mb-3">Pending Queue</h2>
        <Card class="divide-y">
          <div v-for="req in pendingRequests" :key="req.request_id" class="p-3 text-sm">
            <span class="font-medium">#{{ req.request_id }}:</span>
            <span class="ml-2">{{ req.prompt.slice(0, 60) }}{{ req.prompt.length > 60 ? '...' : '' }}</span>
            <span class="ml-2 text-muted-foreground">({{ req.fee }} udys)</span>
          </div>
        </Card>
      </div>

      <!-- All Requests -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-lg font-semibold">All Requests</h2>
          <div class="flex gap-1">
            <button
              v-for="status in ['all', 'pending', 'active', 'revealing', 'finalizing', 'resolved', 'failed']"
              :key="status"
              @click="statusFilter = status"
              class="px-2 py-1 text-xs rounded transition-colors"
              :class="statusFilter === status 
                ? 'bg-primary text-primary-foreground' 
                : 'bg-muted hover:bg-muted/80'"
            >
              {{ status }} ({{ statusCounts[status] || 0 }})
            </button>
          </div>
        </div>
        <div v-if="filteredRequests.length === 0" class="text-muted-foreground">
          {{ requests.length === 0 ? 'No requests yet' : 'No requests match filter' }}
        </div>
        <Card v-else class="divide-y">
          <router-link
            v-for="req in filteredRequests"
            :key="req.request_id"
            :to="`/request/${req.request_id}`"
            class="block p-3 hover:bg-muted/50"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium">#{{ req.request_id }}: {{ req.prompt.slice(0, 50) }}{{ req.prompt.length > 50 ? '...' : '' }}</span>
              <span 
                class="px-2 py-0.5 text-xs rounded"
                :class="{
                  'bg-yellow-100 text-yellow-800': getEffectiveStatus(req) === 'pending',
                  'bg-blue-100 text-blue-800': getEffectiveStatus(req) === 'active',
                  'bg-purple-100 text-purple-800': getEffectiveStatus(req) === 'revealing',
                  'bg-orange-100 text-orange-800': getEffectiveStatus(req) === 'finalizing',
                  'bg-green-100 text-green-800': getEffectiveStatus(req) === 'resolved',
                  'bg-red-100 text-red-800': getEffectiveStatus(req) === 'failed',
                }"
              >
                {{ getEffectiveStatus(req) }}
              </span>
            </div>
          </router-link>
        </Card>
      </div>

      <!-- Providers Link -->
      <router-link to="/providers" class="block">
        <Card class="p-4 hover:bg-muted/50 transition-colors">
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-lg font-semibold">Providers</h2>
              <p class="text-sm text-muted-foreground">
                {{ activeProviders().length }} active, {{ providers.length }} total registered
              </p>
            </div>
            <span class="text-primary">View All →</span>
          </div>
        </Card>
      </router-link>
    </template>
  </div>
</template>
