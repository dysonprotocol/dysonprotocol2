<script setup lang="ts">
import { cn } from "@/lib/utils";
import { DialogDescription, type DialogDescriptionProps } from "radix-vue";
import { computed } from "vue";

const props = defineProps<DialogDescriptionProps & { class?: string }>();
const delegatedProps = computed(() => { const { class: _, ...rest } = props; return rest; });
</script>

<template>
  <DialogDescription v-bind="delegatedProps" :class="cn('text-sm text-muted-foreground', props.class)">
    <slot />
  </DialogDescription>
</template>

