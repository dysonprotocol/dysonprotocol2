<script setup lang="ts">
import { computed } from "vue";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";

const props = defineProps<{
  address: string | null;
  energyBalance: string;
  hasWarning: boolean;
  isCritical: boolean;
  isEmpty: boolean;
}>();

const emit = defineEmits<{
  (e: "connect"): void;
}>();

const energyClass = computed(() => {
  if (props.isEmpty) return "text-red-400 animate-pulse";
  if (props.isCritical) return "text-orange-400";
  if (props.hasWarning) return "text-amber-400";
  return "text-amber-300";
});
</script>

<template>
  <header
    data-testid="site-header"
    class="bg-background sticky top-0 z-50 flex h-14 shrink-0 items-center gap-2 border-b px-4"
  >
    <SidebarTrigger
      data-testid="sidebar-trigger"
      class="-ml-1 cursor-pointer"
    />
    <Separator orientation="vertical" class="mr-2 h-4" />

    <span class="font-bold text-lg">RPS Royal</span>

    <div class="ml-auto flex items-center gap-3">
      <span v-if="address" :class="['font-mono text-sm', energyClass]">
        ⚡ {{ energyBalance }}
      </span>
      <Button v-else size="sm" @click="emit('connect')"> Connect </Button>
    </div>
  </header>
</template>
