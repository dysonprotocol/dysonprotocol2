<script setup lang="ts">
import { ref, computed, toRef, onUnmounted } from "vue";
import { RouterLink } from "vue-router";
import { toast } from "vue-sonner";
import { useWallet } from "@/composables/useWallet";
import {
  useGameState,
  useOwnedTokens,
  useEnergyBalance,
  useMoveMutation,
  useGrid,
} from "@/composables/useRpsGame";
import { Button } from "@/components/ui/button";
import TxLog from "@/components/game/TxLog.vue";
import { transactionConfig } from "@/utils/transactionModalConfig.js";

const { wallet, openWalletDialog } = useWallet();
const address = computed(() => wallet.value?.address || null);

const { data: gameState } = useGameState();
const { data: ownedTokens } = useOwnedTokens(toRef(() => address.value));
const { data: energyBalance } = useEnergyBalance(toRef(() => address.value));
const { bounds } = useGrid(
  toRef(() => gameState.value),
  toRef(() => address.value)
);
const moveMutation = useMoveMutation();

const isRunning = ref(false);
const moveCount = ref(0);
const lastMove = ref<string | null>(null);
let timeoutId: ReturnType<typeof setTimeout> | null = null;

// Store original modal handler to restore later
let originalModalHandler: typeof transactionConfig.modalHandler = null;

// Auto-approve handler that skips the dialog
function autoApproveHandler(msgs: any, memo: string, fee: any) {
  return Promise.resolve({ msgs, memo, fee });
}

const energyNum = computed(() => parseInt(energyBalance.value || "0", 10));

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function getOccupiedCells(): Set<string> {
  const occupied = new Set<string>();
  const tokens = gameState.value?.tokens || {};
  for (const t of Object.values(tokens)) {
    occupied.add(`${t.x},${t.y}`);
  }
  return occupied;
}

async function moveRandomPiece() {
  if (!isRunning.value) return;

  const pieces = ownedTokens.value;
  if (!pieces?.length) {
    lastMove.value = "No pieces owned";
    scheduleNext();
    return;
  }

  const piece = pieces[randomInt(0, pieces.length - 1)];
  const occupied = getOccupiedCells();
  const { min, max } = bounds.value;

  // Pick random target (adjacent for free move, or jump if energy allows)
  let targetX = piece.x;
  let targetY = piece.y;
  let attempts = 0;
  const maxAttempts = 50;

  do {
    // Prefer adjacent moves (80%) vs jumps (20%)
    if (Math.random() < 0.8) {
      // Adjacent move
      const dx = randomInt(-1, 1);
      const dy = randomInt(-1, 1);
      targetX = piece.x + dx;
      targetY = piece.y + dy;
    } else {
      // Jump (random location within bounds)
      targetX = randomInt(min, max);
      targetY = randomInt(min, max);
    }
    attempts++;
  } while (
    (occupied.has(`${targetX},${targetY}`) ||
      targetX < min ||
      targetX > max ||
      targetY < min ||
      targetY > max ||
      (targetX === piece.x && targetY === piece.y)) &&
    attempts < maxAttempts
  );

  if (attempts >= maxAttempts) {
    lastMove.value = "No valid target found";
    scheduleNext();
    return;
  }

  const dx = targetX - piece.x;
  const dy = targetY - piece.y;
  const cost = dx * dx + dy * dy;
  const isAdjacent = Math.abs(dx) <= 1 && Math.abs(dy) <= 1;

  // Check energy for jumps
  if (!isAdjacent && cost > energyNum.value) {
    lastMove.value = `Skip jump (need ${cost}⚡, have ${energyNum.value}⚡)`;
    scheduleNext();
    return;
  }

  const moveType = isAdjacent ? "walk" : `jump (${cost}⚡)`;
  lastMove.value = `#${piece.id} → (${targetX}, ${targetY}) ${moveType}`;

  try {
    await moveMutation.mutateAsync({ pieceId: piece.id, targetX, targetY });
    moveCount.value++;
    toast.success(`Moved #${piece.id} to (${targetX}, ${targetY})`);
  } catch (err) {
    lastMove.value = `Failed: ${err instanceof Error ? err.message : err}`;
  }

  scheduleNext();
}

function scheduleNext() {
  if (!isRunning.value) return;
  timeoutId = setTimeout(moveRandomPiece, 2000 + Math.random() * 1000);
}

function start() {
  if (!address.value) {
    openWalletDialog();
    return;
  }
  // Save original handler and set auto-approve
  originalModalHandler = transactionConfig.modalHandler;
  transactionConfig.modalHandler = autoApproveHandler;
  isRunning.value = true;
  moveRandomPiece();
}

function stop() {
  isRunning.value = false;
  // Restore original modal handler
  transactionConfig.modalHandler = originalModalHandler;
  if (timeoutId) {
    clearTimeout(timeoutId);
    timeoutId = null;
  }
}

onUnmounted(stop);
</script>

<template>
  <div class="min-h-screen bg-zinc-950 text-zinc-100 p-8">
    <header class="flex items-center justify-between mb-8">
      <h1
        class="text-3xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent"
      >
        🤖 Autopilot
      </h1>
      <RouterLink to="/" class="text-zinc-400 hover:text-zinc-200 transition">
        ← Back to Game
      </RouterLink>
    </header>

    <div class="max-w-md mx-auto space-y-6">
      <!-- Status Card -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-zinc-400">Status</span>
          <span :class="isRunning ? 'text-emerald-400' : 'text-zinc-500'">
            {{ isRunning ? "● Running" : "○ Stopped" }}
          </span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-zinc-400">Moves Made</span>
          <span class="font-mono">{{ moveCount }}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-zinc-400">Pieces Owned</span>
          <span class="font-mono">{{ ownedTokens?.length || 0 }}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-zinc-400">Energy</span>
          <span class="font-mono text-amber-400">⚡ {{ energyNum }}</span>
        </div>
        <div v-if="lastMove" class="pt-2 border-t border-zinc-800">
          <span class="text-zinc-500 text-sm">Last: </span>
          <span class="text-zinc-300 text-sm font-mono">{{ lastMove }}</span>
        </div>
      </div>

      <!-- Controls -->
      <div class="flex gap-4">
        <Button
          v-if="!isRunning"
          class="flex-1 bg-emerald-600 hover:bg-emerald-500"
          @click="start"
          :disabled="!address"
        >
          {{ address ? "Start Autopilot" : "Connect Wallet" }}
        </Button>
        <Button v-else class="flex-1 bg-red-600 hover:bg-red-500" @click="stop">
          Stop
        </Button>
      </div>

      <!-- Info -->
      <p class="text-zinc-500 text-sm text-center">
        Autopilot randomly moves your pieces every 2-3 seconds.<br />
        80% adjacent walks (free) · 20% jumps (costs energy)
      </p>

      <!-- Transaction Log -->
      <div>
        <TxLog />
      </div>
    </div>
  </div>
</template>
