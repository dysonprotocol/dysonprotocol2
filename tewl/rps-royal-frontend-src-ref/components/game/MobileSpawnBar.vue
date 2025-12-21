<script setup lang="ts">
import { computed } from "vue";
import { JOIN_COST, type Token, type TokenTypeName } from "@/types/game";

const props = defineProps<{
  ownedPieces?: Token[];
  energyBalance: number;
  isSpawning: boolean;
  isConnected: boolean;
}>();

const emit = defineEmits<{
  (e: "spawn", type: TokenTypeName): void;
  (e: "connect"): void;
}>();

const pieces = computed(() => props.ownedPieces || []);
const canAfford = computed(() => props.energyBalance >= JOIN_COST);

const rockCount = computed(
  () => pieces.value.filter((p) => p.type === "rock").length
);
const paperCount = computed(
  () => pieces.value.filter((p) => p.type === "paper").length
);
const scissorsCount = computed(
  () => pieces.value.filter((p) => p.type === "scissors").length
);

const buttonClass = computed(() => {
  const base =
    "flex-1 flex flex-col items-center justify-center py-2 rounded-lg transition-all min-h-[56px]";
  const disabled = "opacity-40 cursor-not-allowed";
  const enabled = "cursor-pointer active:scale-95";
  return props.isSpawning || !canAfford.value
    ? `${base} ${disabled}`
    : `${base} ${enabled}`;
});
</script>

<template>
  <!-- Mobile: full width | Desktop: centered floating -->
  <div
    class="fixed bottom-0 z-40 left-0 right-0 md:left-1/2 md:-translate-x-1/2 md:right-auto md:bottom-4 md:rounded-xl md:min-w-80 bg-card/95 backdrop-blur-sm border-t md:border border-border px-4 py-2 pb-safe md:pb-3 md:pt-3 md:px-6 md:shadow-xl"
  >
    <div v-if="isConnected" class="flex gap-3">
      <!-- Rock -->
      <button
        :class="[
          buttonClass,
          'border border-amber-700/50 hover:bg-amber-900/20',
        ]"
        :disabled="isSpawning || !canAfford"
        @click="emit('spawn', 'rock')"
      >
        <span class="text-2xl">🪨</span>
        <span class="text-sm font-mono text-amber-300">×{{ rockCount }}</span>
      </button>

      <!-- Paper -->
      <button
        :class="[buttonClass, 'border border-blue-600/50 hover:bg-blue-900/20']"
        :disabled="isSpawning || !canAfford"
        @click="emit('spawn', 'paper')"
      >
        <span class="text-2xl">📄</span>
        <span class="text-sm font-mono text-blue-300">×{{ paperCount }}</span>
      </button>

      <!-- Scissors -->
      <button
        :class="[buttonClass, 'border border-red-600/50 hover:bg-red-900/20']"
        :disabled="isSpawning || !canAfford"
        @click="emit('spawn', 'scissors')"
      >
        <span class="text-2xl">✂️</span>
        <span class="text-sm font-mono text-red-300">×{{ scissorsCount }}</span>
      </button>
    </div>

    <!-- Not connected -->
    <div v-else class="flex justify-center">
      <button
        class="px-6 py-3 bg-primary text-primary-foreground rounded-lg font-medium"
        @click="emit('connect')"
      >
        Connect Wallet to Play
      </button>
    </div>

    <!-- Can't afford hint -->
    <div
      v-if="isConnected && !canAfford"
      class="text-center text-xs text-muted-foreground mt-1"
    >
      Need {{ JOIN_COST }}⚡ to spawn
    </div>
  </div>
</template>
