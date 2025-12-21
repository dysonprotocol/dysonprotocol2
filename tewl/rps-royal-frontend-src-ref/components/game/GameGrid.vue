<script setup lang="ts">
import { computed } from 'vue'
import { TYPE_EMOJIS, type Token, type Snail } from '@/types/game'

const props = defineProps<{
  grid: (Token | null)[][]
  snailPositions: Map<string, Snail>
  selectedToken: Token | null
  playerAddress: string | null
  bounds: { min: number; max: number }
}>()

const emit = defineEmits<{
  cellClick: [x: number, y: number, token: Token | null]
  tokenSelect: [token: Token]
}>()

// Dynamic sizing based on grid
const gridSize = computed(() => props.grid.length)

// Responsive cell sizing - smaller cells for larger grids
const CELL_SIZE = computed(() => {
  const size = gridSize.value
  if (size <= 21) return 32
  if (size <= 41) return 20
  return 14
})

const GAP = 1
const PADDING = 4

const viewBoxSize = computed(() => gridSize.value * (CELL_SIZE.value + GAP) + PADDING * 2)

function cellX(col: number) {
  return PADDING + col * (CELL_SIZE.value + GAP)
}

function cellY(row: number) {
  return PADDING + row * (CELL_SIZE.value + GAP)
}

function getCellClass(token: Token | null): string {
  if (!token) return 'fill-secondary/40'
  if (token.state === 'pending_battle') return 'fill-destructive/60 animate-pulse'
  if (token.owner === props.playerAddress) return 'fill-primary/30'
  return 'fill-accent/50'
}

function handleCellClick(gridX: number, gridY: number, token: Token | null) {
  if (token && token.owner === props.playerAddress) {
    emit('tokenSelect', token)
  } else {
    emit('cellClick', gridX, gridY, token)
  }
}

// Show coordinate label for origin
function isOrigin(gridX: number, gridY: number): boolean {
  return (gridX + props.bounds.min === 0) && (gridY + props.bounds.min === 0)
}

// World coordinates for display
function worldCoord(gridIndex: number): number {
  return gridIndex + props.bounds.min
}
</script>

<template>
  <div class="flex flex-col items-center gap-1">
    <!-- Bounds label -->
    <div class="text-xs text-muted-foreground font-mono">
      ({{ bounds.min }}, {{ bounds.min }}) to ({{ bounds.max }}, {{ bounds.max }})
    </div>
    
    <svg
      :viewBox="`0 0 ${viewBoxSize} ${viewBoxSize}`"
      class="w-full max-w-[min(100vw-2rem,100vh-12rem)] aspect-square touch-none select-none"
    >
      <!-- Grid cells -->
      <g v-for="(row, y) in grid" :key="y">
        <g v-for="(token, x) in row" :key="x">
          <!-- Cell background -->
          <rect
            :x="cellX(x)"
            :y="cellY(y)"
            :width="CELL_SIZE"
            :height="CELL_SIZE"
            :rx="2"
            :class="[
              getCellClass(token),
              isOrigin(x, y) ? 'stroke-foreground/50 stroke-1' : 'stroke-border stroke-[0.5]'
            ]"
            class="cursor-pointer transition-colors duration-150"
            @click="handleCellClick(x, y, token)"
          />

          <!-- Origin marker -->
          <text
            v-if="isOrigin(x, y) && !token"
            :x="cellX(x) + CELL_SIZE / 2"
            :y="cellY(y) + CELL_SIZE / 2"
            text-anchor="middle"
            dominant-baseline="central"
            class="fill-muted-foreground/40 text-[8px] pointer-events-none select-none font-mono"
          >
            0
          </text>

          <!-- Snail indicator -->
          <circle
            v-if="snailPositions.has(`${x},${y}`)"
            :cx="cellX(x) + CELL_SIZE / 2"
            :cy="cellY(y) + CELL_SIZE / 2"
            :r="CELL_SIZE / 3"
            class="fill-[oklch(0.6_0.12_80/0.3)] pointer-events-none"
          />

          <!-- Token emoji -->
          <text
            v-if="token"
            :x="cellX(x) + CELL_SIZE / 2"
            :y="cellY(y) + CELL_SIZE / 2 + 1"
            text-anchor="middle"
            dominant-baseline="central"
            :class="['pointer-events-none select-none', CELL_SIZE >= 28 ? 'text-[18px]' : 'text-[12px]']"
          >
            {{ TYPE_EMOJIS[token.type] || '?' }}
          </text>

          <!-- Snail emoji (if no token) -->
          <text
            v-else-if="snailPositions.has(`${x},${y}`)"
            :x="cellX(x) + CELL_SIZE / 2"
            :y="cellY(y) + CELL_SIZE / 2 + 1"
            text-anchor="middle"
            dominant-baseline="central"
            :class="['pointer-events-none select-none', CELL_SIZE >= 28 ? 'text-[14px]' : 'text-[10px]']"
          >
            🐌
          </text>

          <!-- Selection ring -->
          <rect
            v-if="selectedToken && token?.id === selectedToken.id"
            :x="cellX(x) - 1"
            :y="cellY(y) - 1"
            :width="CELL_SIZE + 2"
            :height="CELL_SIZE + 2"
            :rx="3"
            fill="none"
            class="stroke-ring stroke-2 pointer-events-none"
          />

          <!-- Energy bar (only if cell is large enough) -->
          <rect
            v-if="token && token.energy > 0 && CELL_SIZE >= 20"
            :x="cellX(x) + 2"
            :y="cellY(y) + CELL_SIZE - 4"
            :width="(CELL_SIZE - 4) * Math.min(token.energy / 100, 1)"
            :height="2"
            :rx="1"
            class="fill-[var(--energy)] pointer-events-none"
          />
        </g>
      </g>
    </svg>
  </div>
</template>
