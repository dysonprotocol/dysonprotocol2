<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { TokenType, TYPE_EMOJIS, JOIN_COST, type TokenTypeName } from '@/types/game'

const props = defineProps<{
  open: boolean
  isSpawning: boolean
  energyBalance?: number
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  spawn: [tokenType: TokenTypeName]
}>()

const selectedType = ref<TokenTypeName>('ROCK')

const canAffordSpawn = computed(() => (props.energyBalance ?? 0) >= JOIN_COST)

const types: { name: TokenTypeName; emoji: string; beats: string }[] = [
  { name: 'ROCK', emoji: TYPE_EMOJIS[TokenType.ROCK], beats: 'Scissors' },
  { name: 'PAPER', emoji: TYPE_EMOJIS[TokenType.PAPER], beats: 'Rock' },
  { name: 'SCISSORS', emoji: TYPE_EMOJIS[TokenType.SCISSORS], beats: 'Paper' },
]

function handleSpawn() {
  if (!canAffordSpawn.value) return
  emit('spawn', selectedType.value)
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-xs">
      <DialogHeader>
        <DialogTitle>Spawn Piece</DialogTitle>
        <DialogDescription>
          Choose your piece type (spawns at random location)
        </DialogDescription>
      </DialogHeader>

      <div class="flex justify-center gap-3 py-4">
        <button
          v-for="t in types"
          :key="t.name"
          :class="[
            'flex flex-col items-center gap-1 p-3 rounded-lg border-2 transition-all',
            selectedType === t.name
              ? 'border-primary bg-primary/10'
              : 'border-border hover:border-muted-foreground',
          ]"
          @click="selectedType = t.name"
        >
          <span class="text-3xl">{{ t.emoji }}</span>
          <span class="text-xs text-muted-foreground">{{ t.name }}</span>
        </button>
      </div>

      <div class="text-center text-sm text-muted-foreground mb-2">
        Cost: <span class="font-semibold text-amber-500">{{ JOIN_COST }}⚡</span>
        <span v-if="!canAffordSpawn" class="text-red-500 ml-2">
          (Insufficient balance: {{ energyBalance ?? 0 }}⚡)
        </span>
      </div>

      <DialogFooter>
        <Button
          class="w-full"
          :disabled="isSpawning || !canAffordSpawn"
          @click="handleSpawn"
        >
          {{ isSpawning ? 'Spawning...' : canAffordSpawn ? 'Spawn' : 'Not Enough Energy' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>



