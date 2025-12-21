<script setup lang="ts">
import { cn } from "@/lib/utils";
import { computed, useAttrs } from "vue";

defineOptions({ inheritAttrs: false });

const props = defineProps<{ class?: string; modelValue?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const attrs = useAttrs();

const classes = computed(() =>
  cn(
    "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
    props.class
  )
);
</script>

<template>
  <textarea
    v-bind="attrs"
    :class="classes"
    :value="modelValue"
    @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
  />
</template>
