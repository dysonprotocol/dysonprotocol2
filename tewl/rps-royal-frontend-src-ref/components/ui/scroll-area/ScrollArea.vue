<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="
      cn(
        'relative overflow-hidden',
        props.class,
      )
    "
  >
    <div class="h-full w-full rounded-[inherit] overflow-auto [&>div]:h-full [&>div]:w-full">
      <slot />
    </div>
  </div>
</template>



