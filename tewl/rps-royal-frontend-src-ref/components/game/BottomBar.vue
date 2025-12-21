<script setup lang="ts">
import { ref, computed } from "vue";
import { Button } from "@/components/ui/button";
import {
  TYPE_EMOJIS,
  JOIN_COST,
  type Token,
  type TokenTypeName,
} from "@/types/game";

const props = defineProps<{
  ownedPieces?: Token[];
  dysBalance: string;
  energyBalance: string;
  selectedPieceId: string | number | null;
  isSpawning: boolean;
}>();

const emit = defineEmits<{
  (e: "select-piece", pieceId: string | number): void;
  (e: "spawn", type: TokenTypeName): void;
  (e: "open-spawn-dialog"): void;
}>();

const expanded = ref(false);

const pieces = computed(() => props.ownedPieces || []);
const pieceCount = computed(() => pieces.value.length);
const energyBalanceNum = computed(() =>
  parseInt(props.energyBalance || "0", 10)
);
const canAffordSpawn = computed(() => energyBalanceNum.value >= JOIN_COST);
</script>

<template>
  <div :class="['bottom-bar', { expanded }]">
    <!-- Collapsed Summary -->
    <div class="collapsed-bar" @click="expanded = !expanded">
      <div class="stats">
        <span class="stat energy">⚡ {{ energyBalance }}</span>
        <span class="stat">💎 {{ dysBalance }} DYS</span>
        <span class="stat">🎮 {{ pieceCount }}</span>
      </div>
      <div class="expand-hint">
        <span class="chevron">{{ expanded ? "▼" : "▲" }}</span>
      </div>
      <Button
        variant="outline"
        size="sm"
        class="spawn-btn"
        :disabled="isSpawning"
        @click.stop="emit('open-spawn-dialog')"
      >
        + Spawn
      </Button>
    </div>

    <!-- Expanded Panel -->
    <Transition name="slide-up">
      <div v-if="expanded" class="expanded-panel">
        <!-- Piece List -->
        <div class="piece-list">
          <div class="section-title">Your Pieces</div>
          <div v-if="pieces.length === 0" class="empty-state">
            No pieces yet. Spawn your first piece!
          </div>
          <div
            v-for="piece in pieces"
            :key="piece.id"
            :class="['piece-item', { selected: selectedPieceId === piece.id }]"
            @click="emit('select-piece', piece.id)"
          >
            <span class="piece-emoji">{{
              TYPE_EMOJIS[piece.type] || "❓"
            }}</span>
            <div class="piece-info">
              <div class="piece-id">#{{ piece.id }}</div>
              <div class="piece-position">({{ piece.x }}, {{ piece.y }})</div>
            </div>
          </div>
        </div>

        <!-- Quick Spawn Buttons -->
        <div class="quick-spawn">
          <div class="section-title">
            Quick Spawn
            <span class="spawn-cost" :class="{ affordable: canAffordSpawn }">
              {{ JOIN_COST }}⚡
            </span>
          </div>
          <div class="spawn-buttons">
            <button
              class="type-btn rock"
              :disabled="isSpawning || !canAffordSpawn"
              :title="
                canAffordSpawn
                  ? 'Spawn Rock'
                  : `Need ${JOIN_COST}⚡ (have ${energyBalanceNum})`
              "
              @click="emit('spawn', 'rock')"
            >
              🪨
            </button>
            <button
              class="type-btn paper"
              :disabled="isSpawning || !canAffordSpawn"
              :title="
                canAffordSpawn
                  ? 'Spawn Paper'
                  : `Need ${JOIN_COST}⚡ (have ${energyBalanceNum})`
              "
              @click="emit('spawn', 'paper')"
            >
              📄
            </button>
            <button
              class="type-btn scissors"
              :disabled="isSpawning || !canAffordSpawn"
              :title="
                canAffordSpawn
                  ? 'Spawn Scissors'
                  : `Need ${JOIN_COST}⚡ (have ${energyBalanceNum})`
              "
              @click="emit('spawn', 'scissors')"
            >
              ✂️
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  background: hsl(var(--card) / 0.95);
  backdrop-filter: blur(8px);
  border-top: 1px solid hsl(var(--border));
  transition: all 0.3s ease;
}

.collapsed-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
}

.stats {
  display: flex;
  gap: 16px;
}

.stat {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.stat.energy {
  color: hsl(45 100% 50%);
  font-weight: 600;
}

.expand-hint {
  flex: 1;
  display: flex;
  justify-content: center;
}

.chevron {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  transition: transform 0.3s ease;
}

.expanded .chevron {
  transform: rotate(180deg);
}

.spawn-btn {
  margin-left: 8px;
}

.expanded-panel {
  padding: 0 16px 16px;
  max-height: 300px;
  overflow-y: auto;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: hsl(var(--muted-foreground));
  margin: 12px 0 8px;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.spawn-cost {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: hsl(0 50% 50% / 0.2);
  color: hsl(0 70% 50%);
}

.spawn-cost.affordable {
  background: hsl(142 50% 40% / 0.2);
  color: hsl(142 70% 45%);
}

.piece-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.empty-state {
  color: hsl(var(--muted-foreground));
  font-size: 14px;
  text-align: center;
  padding: 12px;
}

.piece-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: hsl(var(--secondary) / 0.5);
  cursor: pointer;
  transition: all 0.15s ease;
}

.piece-item:hover {
  background: hsl(var(--secondary));
}

.piece-item.selected {
  background: hsl(var(--primary) / 0.2);
  border: 1px solid hsl(var(--primary) / 0.5);
}

.piece-emoji {
  font-size: 24px;
}

.piece-info {
  flex: 1;
}

.piece-id {
  font-weight: 600;
  font-size: 14px;
}

.piece-position {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  font-family: monospace;
}

.quick-spawn {
  margin-top: 8px;
}

.spawn-buttons {
  display: flex;
  gap: 8px;
}

.type-btn {
  flex: 1;
  padding: 12px;
  font-size: 24px;
  border: 2px solid transparent;
  border-radius: 8px;
  background: hsl(var(--secondary));
  cursor: pointer;
  transition: all 0.15s ease;
}

.type-btn:hover:not(:disabled) {
  transform: scale(1.05);
}

.type-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.type-btn.rock {
  border-color: hsl(30 50% 40%);
}

.type-btn.rock:hover:not(:disabled) {
  background: hsl(30 50% 40% / 0.2);
}

.type-btn.paper {
  border-color: hsl(210 50% 60%);
}

.type-btn.paper:hover:not(:disabled) {
  background: hsl(210 50% 60% / 0.2);
}

.type-btn.scissors {
  border-color: hsl(0 50% 50%);
}

.type-btn.scissors:hover:not(:disabled) {
  background: hsl(0 50% 50% / 0.2);
}

/* Slide up animation */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
</style>
