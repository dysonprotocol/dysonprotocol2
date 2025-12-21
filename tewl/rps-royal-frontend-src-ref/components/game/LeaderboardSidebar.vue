<script setup lang="ts">
import { ref } from "vue";
import { useLeaderboardSections } from "@/composables/useLeaderboard";

const props = defineProps<{
  currentAddress: string | null;
}>();

const collapsed = ref(false);
const { sections, playerCount, isLoading } = useLeaderboardSections(3);

function toggleCollapsed() {
  collapsed.value = !collapsed.value;
}

function isCurrentPlayer(truncatedAddr: string): boolean {
  if (!props.currentAddress) return false;
  // Address is formatted as "dys1a2...x3y4" (first 6 + last 4)
  const parts = truncatedAddr.split("...");
  if (parts.length !== 2) return false;
  return (
    props.currentAddress.startsWith(parts[0]) &&
    props.currentAddress.endsWith(parts[1])
  );
}
</script>

<template>
  <aside
    data-testid="leaderboard-sidebar"
    :class="[
      'hidden md:flex flex-col h-full bg-sidebar border-l border-border transition-all duration-200',
      collapsed ? 'w-12' : 'w-64',
    ]"
  >
    <!-- Header with toggle -->
    <div class="p-3 flex items-center justify-between border-b border-border">
      <span v-if="!collapsed" class="text-base font-bold">🏆 Leaderboard</span>
      <button
        class="p-1 rounded hover:bg-secondary transition-colors cursor-pointer"
        :title="collapsed ? 'Expand' : 'Collapse'"
        @click="toggleCollapsed"
      >
        <svg
          :class="['w-4 h-4 transition-transform', collapsed ? 'rotate-180' : '']"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 5l7 7-7 7"
          />
        </svg>
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-2">
      <!-- Loading -->
      <div
        v-if="isLoading"
        class="text-center text-muted-foreground text-sm py-4 animate-pulse"
      >
        Loading...
      </div>

      <!-- Expanded view -->
      <template v-else-if="!collapsed">
        <div
          class="text-xs text-muted-foreground text-center mb-3"
        >
          {{ playerCount }} players
        </div>

        <!-- Category Sections -->
        <div class="space-y-3">
          <div v-for="section in sections" :key="section.id">
            <!-- Section Header -->
            <div
              class="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1 mb-1"
            >
              <span>{{ section.icon }}</span>
              <span>{{ section.desc }}</span>
            </div>

            <!-- Empty state -->
            <div
              v-if="section.entries.length === 0"
              class="text-xs text-muted-foreground/50 pl-4"
            >
              —
            </div>

            <!-- Top 3 -->
            <div v-else class="space-y-0.5">
              <div
                v-for="entry in section.entries"
                :key="entry.address"
                :class="[
                  'flex items-center gap-1.5 px-1.5 py-1 rounded text-xs',
                  isCurrentPlayer(entry.address)
                    ? 'bg-primary/10'
                    : 'bg-secondary/20',
                ]"
              >
                <!-- Rank medal -->
                <span class="w-4 text-center">
                  {{ entry.rank === 1 ? "🥇" : entry.rank === 2 ? "🥈" : "🥉" }}
                </span>

                <!-- Address -->
                <span
                  class="flex-1 font-mono truncate"
                  :class="
                    isCurrentPlayer(entry.address)
                      ? 'text-foreground'
                      : 'text-foreground/70'
                  "
                >
                  {{ entry.address }}
                </span>

                <!-- Value -->
                <span class="text-muted-foreground font-medium">
                  {{ entry.label }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Collapsed view -->
      <template v-else>
        <div class="flex flex-col items-center gap-2">
          <span
            v-for="section in sections"
            :key="section.id"
            :title="section.name"
            class="text-sm"
          >
            {{ section.icon }}
          </span>
        </div>
      </template>
    </div>
  </aside>
</template>

