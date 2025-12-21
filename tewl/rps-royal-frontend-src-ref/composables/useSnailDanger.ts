/**
 * useSnailDanger - Detects when player's piece is the snail's target
 *
 * The snail targets the OLDEST piece on the board (lowest ID that's still alive)
 */

import { computed, type Ref } from "vue";
import type { GameState, Token } from "@/types/game";
import { walkMoveCount } from "@/utils/pathfinding";

export interface SnailDangerState {
  isTargeted: boolean;
  snailPosition: { x: number; y: number } | null;
  targetPiece: Token | null;
  distanceToTarget: number;
}

export function useSnailDanger(
  gameState: Ref<GameState | null>,
  playerAddress: Ref<string | null>
) {
  // Find the snail in the game
  const snail = computed(() => {
    if (!gameState.value?.tokens) return null;
    
    for (const token of Object.values(gameState.value.tokens)) {
      if (token.type === "snail") {
        return token;
      }
    }
    return null;
  });

  // Find the oldest piece (lowest ID = first spawned = oldest)
  const oldestPiece = computed(() => {
    if (!gameState.value?.tokens) return null;
    
    let oldest: Token | null = null;
    let lowestId = Infinity;
    
    for (const token of Object.values(gameState.value.tokens)) {
      // Skip snail and energy pieces
      if (token.type === "snail" || token.type === "energy") continue;
      
      const numId = typeof token.id === "string" ? parseInt(token.id, 10) : token.id;
      if (numId < lowestId) {
        lowestId = numId;
        oldest = token;
      }
    }
    
    return oldest;
  });

  // Check if player owns the oldest piece
  const isPlayerTargeted = computed(() => {
    if (!oldestPiece.value || !playerAddress.value) return false;
    return oldestPiece.value.owner === playerAddress.value;
  });

  // Calculate distance from snail to target
  const distanceToTarget = computed(() => {
    if (!snail.value || !oldestPiece.value) return 0;
    
    return walkMoveCount(
      { x: snail.value.x, y: snail.value.y },
      { x: oldestPiece.value.x, y: oldestPiece.value.y }
    );
  });

  // Full danger state
  const dangerState = computed<SnailDangerState>(() => ({
    isTargeted: isPlayerTargeted.value,
    snailPosition: snail.value ? { x: snail.value.x, y: snail.value.y } : null,
    targetPiece: oldestPiece.value,
    distanceToTarget: distanceToTarget.value,
  }));

  return {
    snail,
    oldestPiece,
    isPlayerTargeted,
    distanceToTarget,
    dangerState,
  };
}

