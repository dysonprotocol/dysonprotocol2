<script setup lang="ts">
import { cn } from "@/lib/utils";
import { DialogTitle, type DialogTitleProps } from "radix-vue";
import { computed } from "vue";

const props = defineProps<DialogTitleProps & { class?: string }>();
const delegatedProps = computed(() => { const { class: _, ...rest } = props; return rest; });
</script>

<template>
  <DialogTitle v-bind="delegatedProps" :class="cn('text-lg font-semibold leading-none tracking-tight', props.class)">
    <slot />
  </DialogTitle>
</template>

