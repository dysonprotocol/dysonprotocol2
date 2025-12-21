<script setup lang="ts">
import { computed } from "vue";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import TxLog from "@/components/game/TxLog.vue";
import EnergyMarket from "@/components/game/EnergyMarket.vue";
import { JOIN_COST, type Token, type TokenTypeName } from "@/types/game";

interface PendingMove {
  pieceId: number;
  fromX: number;
  fromY: number;
  targetX: number;
  targetY: number;
  executor: string;
}

const props = defineProps<{
  address: string | null;
  dysBalance: string;
  energyBalance: string;
  justCopied: boolean;
  tick: number;
  totalPieces: number;
  gridSize: number;
  ownedPieces?: Token[];
  selectedPieceId: string | number | null;
  isSpawning: boolean;
  pendingMoves: PendingMove[];
  isMempoolPolling: boolean;
  mempoolError: string | null;
  hasWarning: boolean;
  isCritical: boolean;
  isEmpty: boolean;
  warningMessage?: string;
}>();

const emit = defineEmits<{
  (e: "connect"): void;
  (e: "disconnect"): void;
  (e: "copy-address"): void;
  (e: "select-piece", pieceId: string | number): void;
  (e: "spawn", type: TokenTypeName): void;
}>();

const pieces = computed(() => props.ownedPieces || []);
const energyBalanceNum = computed(() =>
  parseInt(props.energyBalance || "0", 10)
);
const canAffordSpawn = computed(() => energyBalanceNum.value >= JOIN_COST);

const rockPieces = computed(() =>
  pieces.value.filter((p) => p.type === "rock")
);
const paperPieces = computed(() =>
  pieces.value.filter((p) => p.type === "paper")
);
const scissorPieces = computed(() =>
  pieces.value.filter((p) => p.type === "scissors")
);

const energyClass = computed(() => {
  if (props.isEmpty) return "bg-red-500/20 border-red-500/50";
  if (props.isCritical) return "bg-orange-500/20 border-orange-500/50";
  if (props.hasWarning) return "bg-amber-500/20 border-amber-500/50";
  return "bg-amber-500/10 border-transparent";
});
</script>

<template>
  <Sidebar data-testid="app-sidebar" collapsible="icon">
    <SidebarContent>
      <template v-if="address">
        <!-- Wallet -->
        <SidebarGroup>
          <SidebarGroupLabel>Wallet</SidebarGroupLabel>
          <!-- Collapsed icon -->
          <div
            class="hidden group-data-[collapsible=icon]:flex justify-center py-2"
          ></div>
          <SidebarGroupContent>
            <div class="px-2 space-y-3 group-data-[collapsible=icon]:hidden">
              <!-- Balance subsection -->
              <div
                class="text-xs font-semibold text-muted-foreground uppercase tracking-wider"
              >
                Balance
              </div>
              <div
                :class="[
                  'flex justify-between items-center p-2 rounded border',
                  energyClass,
                ]"
              >
                <span class="text-amber-300">⚡ Energy</span>
                <span class="font-mono font-bold text-amber-300">{{
                  energyBalance
                }}</span>
              </div>
              <div
                v-if="warningMessage"
                class="text-xs text-center"
                :class="
                  isEmpty
                    ? 'text-red-400'
                    : isCritical
                    ? 'text-orange-400'
                    : 'text-amber-400'
                "
              >
                {{ warningMessage }}
              </div>
              <div
                class="flex justify-between items-center p-2 rounded bg-secondary/50"
              >
                <span class="text-muted-foreground">DYS</span>
                <span class="font-mono">{{ dysBalance }} DYS</span>
              </div>

              <!-- Address subsection -->
              <div class="pt-3">
                <div
                  class="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2"
                >
                  Address
                </div>
                <button
                  class="w-full flex items-center gap-2 px-3 py-2 rounded bg-secondary/50 hover:bg-secondary transition-colors cursor-pointer"
                  @click="emit('copy-address')"
                >
                  <span
                    class="font-mono text-xs text-foreground/80 flex-1 text-left truncate"
                    >{{ address }}</span
                  >
                  <svg
                    v-if="justCopied"
                    class="w-4 h-4 text-green-500 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  <svg
                    v-else
                    class="w-4 h-4 text-muted-foreground shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                    />
                  </svg>
                </button>
              </div>

              <Button
                variant="ghost"
                size="sm"
                class="w-full text-red-400 hover:text-red-300 hover:bg-red-500/10 cursor-pointer"
                @click="emit('disconnect')"
              >
                Disconnect
              </Button>
            </div>
          </SidebarGroupContent>
        </SidebarGroup>

        <!-- Energy Market -->
        <SidebarGroup class="pt-3">
          <SidebarGroupLabel>Energy Market</SidebarGroupLabel>
          <!-- Collapsed icon -->
          <div
            class="hidden group-data-[collapsible=icon]:flex justify-center py-2"
          ></div>
          <SidebarGroupContent>
            <div class="px-2 group-data-[collapsible=icon]:hidden">
              <EnergyMarket
                :energy-balance="energyBalanceNum"
                :dys-balance="dysBalance"
              />
            </div>
          </SidebarGroupContent>
        </SidebarGroup>
      </template>

      <!-- Activity -->
      <SidebarGroup class="pt-3">
        <SidebarGroupLabel>
          Activity
          <span
            v-if="pendingMoves.length > 0"
            class="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded animate-pulse ml-2"
          >
            {{ pendingMoves.length }}
          </span>
        </SidebarGroupLabel>
        <SidebarGroupContent>
          <div class="px-2 group-data-[collapsible=icon]:hidden">
            <div class="flex items-center gap-2 mb-2">
              <span
                :class="isMempoolPolling ? 'text-green-400' : 'text-red-400'"
              >
                {{ isMempoolPolling ? "⏳" : "⚠️" }}
              </span>
              <span class="text-xs text-muted-foreground">
                Mempool ({{ pendingMoves.length }})
              </span>
            </div>
            <div v-if="mempoolError" class="text-red-400 text-xs mb-2">
              {{ mempoolError }}
            </div>
            <div
              v-if="pendingMoves.length === 0"
              class="text-muted-foreground text-center py-2 text-xs"
            >
              No pending moves
            </div>
            <div v-else class="space-y-1 max-h-32 overflow-y-auto">
              <div
                v-for="(move, idx) in pendingMoves"
                :key="idx"
                class="bg-blue-950/30 border border-blue-800/30 rounded px-2 py-1 text-xs font-mono"
              >
                <div class="flex items-center justify-between gap-2">
                  <span>#{{ move.pieceId }}</span>
                  <span class="text-muted-foreground text-[10px]">
                    ({{ move.fromX }},{{ move.fromY }})→({{ move.targetX }},{{
                      move.targetY
                    }})
                  </span>
                  <span class="text-blue-400">
                    {{
                      Math.abs(move.targetX - move.fromX) <= 1 &&
                      Math.abs(move.targetY - move.fromY) <= 1
                        ? "🚶"
                        : "🦘"
                    }}
                  </span>
                </div>
              </div>
            </div>
            <div class="pt-3 mt-3">
              <TxLog />
            </div>
          </div>
        </SidebarGroupContent>
      </SidebarGroup>

      <!-- Connect (when not connected) -->
      <template v-if="!address">
        <SidebarGroup class="border-t border-border pt-3">
          <SidebarGroupLabel>Account</SidebarGroupLabel>
          <!-- Collapsed icon -->
          <div
            class="hidden group-data-[collapsible=icon]:flex justify-center py-2"
          >
            <span class="text-xl" title="Connect">🔗</span>
          </div>
          <SidebarGroupContent>
            <div class="px-2 group-data-[collapsible=icon]:hidden">
              <Button class="w-full" @click="emit('connect')"> Connect </Button>
            </div>
          </SidebarGroupContent>
        </SidebarGroup>
      </template>
    </SidebarContent>
  </Sidebar>
</template>
