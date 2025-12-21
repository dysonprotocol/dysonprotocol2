/**
 * useCommandQueue - Manages queued commands for piece movement
 *
 * Features:
 * - Queue move_to or follow commands per piece
 * - Calculate path using A* pathfinding
 * - Execute one step per block per piece
 * - Recalculate follow paths each block
 * - Handle blocked paths with alerts
 */

import { reactive, computed, watch, type Ref } from "vue";
import { findPath, type Vec2 } from "@/utils/pathfinding";
import type { GameState, Token } from "@/types/game";

export type CommandType = "move_to" | "follow";

export interface Command {
  type: CommandType;
  pieceId: string | number;
  target: Vec2 | { pieceId: string | number };
  path: Vec2[];
  status: "pending" | "executing" | "blocked" | "completed";
  createdAt: number;
}

export interface CommandQueueState {
  commands: Map<string, Command>;
  lastBlock: number;
}

export function useCommandQueue(
  gameState: Ref<GameState | null>,
  playerAddress: Ref<string | null>
) {
  console.log("[useCommandQueue] Composable created");

  const state = reactive<CommandQueueState>({
    commands: new Map(),
    lastBlock: 0,
  });

  // Get grid bounds from game state (based on actual token count)
  const bounds = computed(() => {
    const tokens = gameState.value?.tokens || {};
    const tokenCount = Object.keys(tokens).length || 10;
    return { min: -tokenCount, max: tokenCount };
  });

  // Get obstacles (all pieces except the moving one)
  function getObstacles(excludePieceId: string | number): Set<string> {
    const obstacles = new Set<string>();
    const tokens = gameState.value?.tokens || {};

    for (const token of Object.values(tokens)) {
      if (String(token.id) !== String(excludePieceId)) {
        obstacles.add(`${token.x},${token.y}`);
      }
    }

    return obstacles;
  }

  // Get piece by ID
  function getPiece(pieceId: string | number): Token | null {
    return gameState.value?.tokens?.[String(pieceId)] || null;
  }

  // Calculate path for a command
  function calculatePath(command: Command): Vec2[] {
    const piece = getPiece(command.pieceId);
    if (!piece) return [];

    let targetPos: Vec2;

    if ("pieceId" in command.target) {
      // Follow mode - get target piece position
      const targetPiece = getPiece(command.target.pieceId);
      if (!targetPiece) return [];
      targetPos = { x: targetPiece.x, y: targetPiece.y };
    } else {
      // Move to position
      targetPos = command.target;
    }

    const start = { x: piece.x, y: piece.y };
    const obstacles = getObstacles(command.pieceId);

    // Don't include target as obstacle (we want to reach it)
    obstacles.delete(`${targetPos.x},${targetPos.y}`);

    return findPath(start, targetPos, obstacles, bounds.value);
  }

  /**
   * Set a move-to destination for a piece
   */
  function setDestination(pieceId: string | number, target: Vec2) {
    const piece = getPiece(pieceId);
    if (!piece) {
      console.warn("[useCommandQueue] Piece not found:", pieceId);
      return;
    }

    // Check if already at destination
    if (piece.x === target.x && piece.y === target.y) {
      console.log("[useCommandQueue] Already at destination");
      return;
    }

    const command: Command = {
      type: "move_to",
      pieceId,
      target,
      path: [],
      status: "pending",
      createdAt: Date.now(),
    };

    command.path = calculatePath(command);

    if (command.path.length === 0) {
      console.warn("[useCommandQueue] No path found to destination");
      command.status = "blocked";
    }

    state.commands.set(String(pieceId), command);
    console.log(
      "[useCommandQueue] Set destination:",
      pieceId,
      "->",
      target,
      "path:",
      command.path.length,
      "steps"
    );
  }

  /**
   * Set a follow target for a piece
   */
  function setFollowTarget(
    pieceId: string | number,
    targetPieceId: string | number
  ) {
    const piece = getPiece(pieceId);
    const targetPiece = getPiece(targetPieceId);

    if (!piece || !targetPiece) {
      console.warn("[useCommandQueue] Piece not found");
      return;
    }

    const command: Command = {
      type: "follow",
      pieceId,
      target: { pieceId: targetPieceId },
      path: [],
      status: "pending",
      createdAt: Date.now(),
    };

    command.path = calculatePath(command);
    state.commands.set(String(pieceId), command);
    console.log("[useCommandQueue] Set follow:", pieceId, "->", targetPieceId);
  }

  /**
   * Cancel command for a piece
   */
  function cancelCommand(pieceId: string | number) {
    state.commands.delete(String(pieceId));
    console.log("[useCommandQueue] Cancelled command for:", pieceId);
  }

  /**
   * Get the next move for a piece (first step in path)
   */
  function getNextMove(pieceId: string | number): Vec2 | null {
    const command = state.commands.get(String(pieceId));
    if (
      !command ||
      command.status === "completed" ||
      command.status === "blocked"
    ) {
      return null;
    }

    // For follow commands, recalculate path each time
    if (command.type === "follow") {
      command.path = calculatePath(command);
    }

    // Path[0] is current position, path[1] is next step
    if (command.path.length >= 2) {
      return command.path[1];
    }

    // If path has only 1 step (current position), we're at destination
    if (command.path.length === 1) {
      command.status = "completed";
      return null;
    }

    // No path
    command.status = "blocked";
    return null;
  }

  /**
   * Mark move as executed, advance path
   */
  function advanceCommand(pieceId: string | number) {
    const command = state.commands.get(String(pieceId));
    if (!command) return;

    // Remove first step (we've moved there)
    if (command.path.length > 0) {
      command.path.shift();
    }

    // Check if completed
    if (command.path.length <= 1) {
      if (command.type === "move_to") {
        command.status = "completed";
        console.log("[useCommandQueue] Command completed:", pieceId);
      }
      // Follow commands continue until cancelled
    }
  }

  /**
   * Get all pending commands
   */
  const pendingCommands = computed(() => {
    const pending: Command[] = [];
    for (const command of state.commands.values()) {
      if (command.status === "pending" || command.status === "executing") {
        pending.push(command);
      }
    }
    return pending;
  });

  /**
   * Check if piece has active command
   */
  function hasCommand(pieceId: string | number): boolean {
    const command = state.commands.get(String(pieceId));
    return command !== undefined && command.status !== "completed";
  }

  /**
   * Get command for piece
   */
  function getCommand(pieceId: string | number): Command | undefined {
    return state.commands.get(String(pieceId));
  }

  // Update paths when game state changes
  watch(
    () => gameState.value?.state?.last_updated_block,
    (newBlock) => {
      if (newBlock && newBlock !== state.lastBlock) {
        state.lastBlock = newBlock;

        // Recalculate paths for all active commands
        for (const command of state.commands.values()) {
          if (command.status === "pending" || command.status === "executing") {
            const newPath = calculatePath(command);
            if (newPath.length === 0 && command.path.length > 0) {
              command.status = "blocked";
              console.log(
                "[useCommandQueue] Path blocked for:",
                command.pieceId
              );
            } else {
              command.path = newPath;
              if (command.status === "blocked" && newPath.length > 0) {
                command.status = "pending";
              }
            }
          }
        }
      }
    }
  );

  return {
    commands: state.commands,
    pendingCommands,
    setDestination,
    setFollowTarget,
    cancelCommand,
    getNextMove,
    advanceCommand,
    hasCommand,
    getCommand,
  };
}
