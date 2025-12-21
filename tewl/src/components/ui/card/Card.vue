<script setup lang="ts">
import { cn } from "@/lib/utils";
import { computed, useAttrs } from "vue";

defineOptions({ inheritAttrs: false });

const props = defineProps<{ class?: string }>();
const attrs = useAttrs();
const classes = computed(() => cn("rounded-lg border bg-card text-card-foreground shadow-sm", props.class));
</script>

<template>
  <div v-bind="attrs" :class="classes">
    <slot />
  </div>
</template>
