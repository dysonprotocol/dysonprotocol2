<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import {
  type Token,
  type DirectionName,
  TYPE_EMOJIS,
} from '@/types/game'

const props = defineProps<{
  token: Token
  isMoving: boolean
  bounds: { min: number; max: number }
}>()

const emit = defineEmits<{
  move: [direction: DirectionName]
  deselect: []
}>()

const canMove = computed(() => {
  const { min, max } = props.bounds
  const moves: Record<DirectionName, boolean> = {
    N: props.token.y > min,
    S: props.token.y < max,
    E: props.token.x < max,
    W: props.token.x > min,
  }
  return moves
})

function handleMove(dir: DirectionName) {
  if (canMove.value[dir] && !props.isMoving) {
    emit('move', dir)
  }
}
</script>

<template>
  <div class="flex flex-col items-center gap-3 p-4 bg-card rounded-xl border border-border">
    <!-- Token info -->
    <div class="flex items-center gap-2 text-lg">
      <span class="text-2xl">{{ TYPE_EMOJIS[token.type] || '?' }}</span>
      <span class="text-muted-foreground text-sm font-mono">
        ({{ token.x }}, {{ token.y }}) · ⚡{{ token.energy }}
      </span>
    </div>

    <!-- D-pad controls -->
    <div class="grid grid-cols-3 gap-1">
      <div />
      <Button
        variant="secondary"
        size="icon"
        :disabled="!canMove.N || isMoving"
        class="h-12 w-12 text-xl"
        @click="handleMove('N')"
      >
        ↑
      </Button>
      <div />
      <Button
        variant="secondary"
        size="icon"
        :disabled="!canMove.W || isMoving"
        class="h-12 w-12 text-xl"
        @click="handleMove('W')"
      >
        ←
      </Button>
      <Button
        variant="outline"
        size="icon"
        class="h-12 w-12 text-xs"
        @click="emit('deselect')"
      >
        ✕
      </Button>
      <Button
        variant="secondary"
        size="icon"
        :disabled="!canMove.E || isMoving"
        class="h-12 w-12 text-xl"
        @click="handleMove('E')"
      >
        →
      </Button>
      <div />
      <Button
        variant="secondary"
        size="icon"
        :disabled="!canMove.S || isMoving"
        class="h-12 w-12 text-xl"
        @click="handleMove('S')"
      >
        ↓
      </Button>
      <div />
    </div>
  </div>
</template>
