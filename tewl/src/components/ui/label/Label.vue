<script setup lang="ts">
import { cn } from "@/lib/utils";
import { computed, useAttrs } from "vue";

defineOptions({ inheritAttrs: false });

const props = defineProps<{ class?: string }>();
const attrs = useAttrs();
const classes = computed(() =>
  cn("text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70", props.class)
);
</script>

<template>
  <label v-bind="attrs" :class="classes">
    <slot />
  </label>
</template>
