/**
 * useBalanceWarnings - Monitors energy balance and triggers warnings
 *
 * Thresholds:
 * - < 100⚡ (JOIN_COST): Cannot spawn new pieces
 * - < 25⚡: Very limited jump range
 * - < 10⚡: Almost no moves possible
 */

import { computed, watch, type Ref } from "vue";
import { toast } from "vue-sonner";
import { JOIN_COST } from "@/types/game";

export type WarningLevel = "none" | "low" | "critical" | "empty";

// Thresholds
const CRITICAL_THRESHOLD = 10;
const LOW_THRESHOLD = 25;

interface BalanceWarningState {
  level: WarningLevel;
  message: string;
  canSpawn: boolean;
  maxAffordableJump: number;
}

export function useBalanceWarnings(energyBalance: Ref<number>) {
  // Track previous level to detect threshold crossings
  let previousLevel: WarningLevel = "none";
  let hasShownInitialWarning = false;

  const warningState = computed<BalanceWarningState>(() => {
    const balance = energyBalance.value;

    if (balance <= 0) {
      return {
        level: "empty",
        message: "No energy! Buy from market or collect grid drops.",
        canSpawn: false,
        maxAffordableJump: 0,
      };
    }

    if (balance < CRITICAL_THRESHOLD) {
      return {
        level: "critical",
        message: `Critical: ${balance}⚡ — Very limited moves`,
        canSpawn: false,
        maxAffordableJump: Math.floor(Math.sqrt(balance)),
      };
    }

    if (balance < LOW_THRESHOLD) {
      return {
        level: "low",
        message: `Low energy: ${balance}⚡ — Limited jump range`,
        canSpawn: false,
        maxAffordableJump: Math.floor(Math.sqrt(balance)),
      };
    }

    if (balance < JOIN_COST) {
      return {
        level: "low",
        message: `${balance}⚡ — Cannot spawn (need ${JOIN_COST})`,
        canSpawn: false,
        maxAffordableJump: Math.floor(Math.sqrt(balance)),
      };
    }

    return {
      level: "none",
      message: "",
      canSpawn: true,
      maxAffordableJump: Math.floor(Math.sqrt(balance)),
    };
  });

  // Watch for threshold crossings and show toasts
  watch(
    () => warningState.value.level,
    (newLevel) => {
      // Skip initial watch if balance is still loading (0)
      if (!hasShownInitialWarning && energyBalance.value === 0) {
        return;
      }
      hasShownInitialWarning = true;

      // Only show toast when crossing into a worse state
      if (newLevel === previousLevel) return;

      const crossedDown =
        (previousLevel === "none" && newLevel !== "none") ||
        (previousLevel === "low" && (newLevel === "critical" || newLevel === "empty")) ||
        (previousLevel === "critical" && newLevel === "empty");

      if (crossedDown) {
        switch (newLevel) {
          case "empty":
            toast.error("⚠️ No energy remaining!", {
              description: "Buy energy from the market or collect grid drops.",
              duration: 5000,
            });
            break;
          case "critical":
            toast.warning("⚠️ Critical energy level!", {
              description: `Only ${energyBalance.value}⚡ — very limited moves.`,
              duration: 4000,
            });
            break;
          case "low":
            toast.warning("Energy getting low", {
              description: `${energyBalance.value}⚡ — consider buying more.`,
              duration: 3000,
            });
            break;
        }
      }

      previousLevel = newLevel;
    },
    { immediate: true }
  );

  return {
    warningState,
    isLow: computed(() => warningState.value.level === "low"),
    isCritical: computed(() => warningState.value.level === "critical"),
    isEmpty: computed(() => warningState.value.level === "empty"),
    hasWarning: computed(() => warningState.value.level !== "none"),
  };
}

