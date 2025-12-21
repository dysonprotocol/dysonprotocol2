<script setup lang="ts">
import { computed, ref, watch, onMounted } from "vue";
import { VisXYContainer, VisLine, VisArea } from "@unovis/vue";

const props = defineProps<{
  value: number;
  color?: string;
  maxPoints?: number;
}>();

const maxPoints = computed(() => props.maxPoints || 20);
const color = computed(() => props.color || "hsl(45 100% 50%)"); // Default amber/gold

// Track history of values
const history = ref<{ x: number; y: number }[]>([]);
let pointIndex = 0;

// Add new value to history when it changes
watch(
  () => props.value,
  (newVal) => {
    history.value = [
      ...history.value.slice(-(maxPoints.value - 1)),
      { x: pointIndex++, y: newVal },
    ];
  },
  { immediate: true }
);

// Initialize with some points if we start with a value
onMounted(() => {
  if (history.value.length === 1) {
    // Pad with initial value
    const initial = history.value[0].y;
    history.value = Array.from({ length: 5 }, (_, i) => ({
      x: i,
      y: initial,
    }));
    pointIndex = 5;
  }
});

const x = (d: { x: number; y: number }) => d.x;
const y = (d: { x: number; y: number }) => d.y;
</script>

<template>
  <div class="h-6 w-16 opacity-80">
    <VisXYContainer :data="history" :margin="{ top: 2, bottom: 2, left: 0, right: 0 }">
      <VisArea :x="x" :y="y" :color="color" :opacity="0.2" :curveType="'monotoneX'" />
      <VisLine :x="x" :y="y" :color="color" :lineWidth="1.5" :curveType="'monotoneX'" />
    </VisXYContainer>
  </div>
</template>

