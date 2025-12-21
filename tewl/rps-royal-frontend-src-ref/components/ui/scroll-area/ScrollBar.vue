<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  orientation?: 'vertical' | 'horizontal'
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="
      cn(
        'flex touch-none select-none transition-colors',
        props.orientation === 'vertical' &&
          'h-full w-2.5 border-l border-l-transparent p-[1px]',
        props.orientation === 'horizontal' &&
          'h-2.5 flex-col border-t border-t-transparent p-[1px]',
        props.class,
      )
    "
  >
    <div
      :class="
        cn(
          'relative flex-1 rounded-full bg-border',
          props.orientation === 'vertical' && 'w-full',
          props.orientation === 'horizontal' && 'h-full',
        )
      "
    />
  </div>
</template>



