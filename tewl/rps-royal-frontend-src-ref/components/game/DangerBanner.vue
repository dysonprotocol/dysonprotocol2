<script setup lang="ts">
import { computed } from "vue";
import type { SnailDangerState } from "@/composables/useSnailDanger";
import { TYPE_EMOJIS } from "@/types/game";

const props = defineProps<{
  dangerState: SnailDangerState;
}>();

const pieceEmoji = computed(() => {
  if (!props.dangerState.targetPiece) return "❓";
  return TYPE_EMOJIS[props.dangerState.targetPiece.type] || "❓";
});
</script>

<template>
  <Transition name="slide-down">
    <div
      v-if="dangerState.isTargeted"
      class="danger-banner"
    >
      <div class="danger-content">
        <span class="danger-icon">⚠️</span>
        <span class="danger-text">YOU ARE THE SNAIL'S TARGET</span>
        <span class="danger-icon">⚠️</span>
      </div>
      <div class="danger-details">
        <span>🐌 → {{ pieceEmoji }}</span>
        <span class="separator">·</span>
        <span>{{ dangerState.distanceToTarget }} cells away</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.danger-banner {
  position: fixed;
  top: 60px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  
  background: linear-gradient(135deg, #c0392b 0%, #e74c3c 50%, #c0392b 100%);
  border: 2px solid #922b21;
  border-radius: 8px;
  padding: 12px 24px;
  
  color: white;
  text-align: center;
  
  box-shadow: 
    0 4px 20px rgba(192, 57, 43, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  
  animation: pulse-danger 2s ease-in-out infinite;
}

.danger-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-weight: bold;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.danger-icon {
  font-size: 18px;
  animation: shake 0.5s ease-in-out infinite;
}

.danger-details {
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.9;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.separator {
  opacity: 0.6;
}

@keyframes pulse-danger {
  0%, 100% {
    box-shadow: 
      0 4px 20px rgba(192, 57, 43, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
  }
  50% {
    box-shadow: 
      0 4px 30px rgba(192, 57, 43, 0.8),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
  }
}

@keyframes shake {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-5deg); }
  75% { transform: rotate(5deg); }
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}
</style>

