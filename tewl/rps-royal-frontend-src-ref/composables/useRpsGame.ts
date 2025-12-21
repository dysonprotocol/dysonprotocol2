import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed, ref, type Ref } from "vue";
import {
  fetchGameState,
  fetchOwnedTokens,
  fetchBalance,
  fetchEnergyBalance,
  fetchAllPieces,
  calculateBoardBounds,
} from "./useRpsApi";
import { useWallet } from "./useWallet";
import { useTxLog } from "./useTxLog";
import {
  SCRIPT_ADDRESS,
  type Token,
  type GameState,
  type TokenTypeName,
} from "@/types/game";

// Parse script response from tx events
function parseScriptResponse(
  events:
    | Array<{
        type: string;
        attributes?: Array<{ key: string; value: string }>;
      }>
    | undefined
): Record<string, unknown> | null {
  if (!Array.isArray(events)) return null;
  const scriptEvt = [...events]
    .reverse()
    .find((e) => e.type === "dysonprotocol.script.v1.EventExecScript");
  if (!scriptEvt?.attributes) return null;

  const responseAttr = scriptEvt.attributes.find((a) => a.key === "response");
  if (!responseAttr?.value) return null;

  try {
    const parsed = JSON.parse(
      responseAttr.value.replace(/(: script execution error)$/, "")
    );
    if (parsed.result && typeof parsed.result === "string") {
      try {
        parsed.result = JSON.parse(parsed.result);
      } catch {
        // ignore parse error
      }
    }
    return parsed.result as Record<string, unknown>;
  } catch {
    return null;
  }
}

export interface MoveResult {
  success: boolean;
  scriptResponse: Record<string, unknown> | null;
  raw: unknown;
}

export function useGameState(refetchInterval: Ref<number> = ref(3000)) {
  return useQuery({
    queryKey: ["gameState"],
    queryFn: fetchGameState,
    refetchInterval,
  });
}

export function useAllPieces() {
  return useQuery({
    queryKey: ["allPieces"],
    queryFn: fetchAllPieces,
    refetchInterval: 3000,
  });
}

export function useOwnedTokens(address: Ref<string | null>) {
  return useQuery({
    queryKey: ["ownedTokens", address],
    queryFn: () => (address.value ? fetchOwnedTokens(address.value) : []),
    enabled: computed(() => !!address.value),
    refetchInterval: 5000,
  });
}

export function useBalance(address: Ref<string | null>) {
  return useQuery({
    queryKey: ["balance", address],
    queryFn: () => (address.value ? fetchBalance(address.value) : "0"),
    enabled: computed(() => !!address.value),
    refetchInterval: 10000,
  });
}

export function useEnergyBalance(address: Ref<string | null>) {
  return useQuery({
    queryKey: ["energyBalance", address],
    queryFn: () => (address.value ? fetchEnergyBalance(address.value) : "0"),
    enabled: computed(() => !!address.value),
    refetchInterval: 5000,
  });
}

export function useSpawnMutation() {
  const queryClient = useQueryClient();
  const { wallet, sendMsg } = useWallet();
  const { addTx, updateTx } = useTxLog();

  return useMutation({
    mutationFn: async ({ tokenType }: { tokenType: TokenTypeName }) => {
      console.log("[SPAWN] Starting spawn mutation for type:", tokenType);

      const txId = addTx({
        functionName: `spawn_piece(${tokenType})`,
        status: "pending",
      });

      // Energy payment (100 rps.dys/energy) is handled via MsgMoveCoins in script
      const msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        executor_address: wallet.value.address,
        script_address: SCRIPT_ADDRESS,
        function_name: "spawn_piece",
        args: "[]",
        kwargs: JSON.stringify({ piece_type: tokenType.toLowerCase() }),
        extra_code: "",
        attached_messages: [],
      };

      try {
        const result = await sendMsg({
          msgs: [msg],
          executorAddress: wallet.value.address!,
          gasLimit: "auto",
        });
        console.log("[SPAWN] sendMsg result:", result);

        updateTx(txId, {
          status: result.success ? "success" : "failed",
          txHash: result.raw?.tx_response?.txhash,
          gasUsed: result.gasUsed,
          gasWanted: result.raw?.tx_response?.gas_wanted,
          rawLog: result.rawLog,
          result: result.success ? result.raw?.tx_response?.data : undefined,
          error: result.success
            ? undefined
            : result.rawLog || "Transaction failed",
        });

        if (!result.success) {
          throw new Error(result.rawLog || "Transaction failed");
        }
        return result;
      } catch (error: any) {
        console.error("[SPAWN] sendMsg error:", error);
        updateTx(txId, {
          status: "failed",
          error: error.message || "Unknown error",
        });
        throw error;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gameState"] });
      queryClient.invalidateQueries({ queryKey: ["ownedTokens"] });
      queryClient.invalidateQueries({ queryKey: ["allPieces"] });
      queryClient.invalidateQueries({ queryKey: ["energyBalance"] });
    },
  });
}

export function useMoveMutation() {
  const queryClient = useQueryClient();
  const { wallet, sendMsg } = useWallet();
  const { addTx, updateTx } = useTxLog();

  return useMutation({
    mutationFn: async ({
      pieceId,
      targetX,
      targetY,
    }: {
      pieceId: number;
      targetX: number;
      targetY: number;
    }): Promise<MoveResult> => {
      console.log("[MOVE] Starting move mutation:", {
        pieceId,
        targetX,
        targetY,
      });

      const txId = addTx({
        functionName: `move_piece(${pieceId} → ${targetX},${targetY})`,
        status: "pending",
      });

      const msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        executor_address: wallet.value.address,
        script_address: SCRIPT_ADDRESS,
        function_name: "move_piece",
        args: "[]",
        kwargs: JSON.stringify({
          piece_id: pieceId,
          target_x: targetX,
          target_y: targetY,
        }),
        extra_code: "",
        attached_messages: [],
      };

      try {
        const result = await sendMsg({
          msgs: [msg],
          executorAddress: wallet.value.address!,
          gasLimit: "auto",
        });
        console.log("[MOVE] sendMsg result:", result);

        updateTx(txId, {
          status: result.success ? "success" : "failed",
          txHash: result.raw?.tx_response?.txhash,
          gasUsed: result.gasUsed,
          gasWanted: result.raw?.tx_response?.gas_wanted,
          rawLog: result.rawLog,
          error: result.success
            ? undefined
            : result.rawLog || "Transaction failed",
        });

        if (!result.success) {
          throw new Error(result.rawLog || "Transaction failed");
        }

        // Parse script response from events
        const events = result.raw?.tx_response?.events;
        const scriptResponse = parseScriptResponse(events);
        console.log("[MOVE] scriptResponse:", scriptResponse);

        return {
          success: true,
          scriptResponse,
          raw: result.raw,
        };
      } catch (error: unknown) {
        console.error("[MOVE] sendMsg error:", error);
        const message =
          error instanceof Error ? error.message : "Unknown error";
        updateTx(txId, {
          status: "failed",
          error: message,
        });
        throw error;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gameState"] });
      queryClient.invalidateQueries({ queryKey: ["ownedTokens"] });
      queryClient.invalidateQueries({ queryKey: ["allPieces"] });
      queryClient.invalidateQueries({ queryKey: ["energyBalance"] });
    },
  });
}

// Dynamic grid state based on game bounds
export function useGrid(
  gameState: Ref<GameState | undefined>,
  playerAddress: Ref<string | null>
) {
  // Calculate dynamic bounds based on actual token count (excludes energy pieces)
  const bounds = computed(() => {
    const tokens = gameState.value?.tokens || {};
    const tokenCount = Object.keys(tokens).length;
    return calculateBoardBounds(tokenCount);
  });

  const gridSize = computed(() => bounds.value.max - bounds.value.min + 1);

  // Build grid from tokens in gameState
  const grid = computed(() => {
    const { min, max } = bounds.value;
    const size = max - min + 1;

    // Create empty grid
    const cells: (Token | null)[][] = Array.from({ length: size }, () =>
      Array(size).fill(null)
    );

    // Place tokens from gameState.tokens
    const tokens = gameState.value?.tokens || {};
    for (const token of Object.values(tokens)) {
      // Convert world coords to grid coords
      const gridX = token.x - min;
      const gridY = token.y - min;

      if (gridX >= 0 && gridX < size && gridY >= 0 && gridY < size) {
        cells[gridY][gridX] = token;
      }
    }

    return cells;
  });

  const snailPositions = computed(() => {
    const map = new Map<string, any>();
    const tokens = gameState.value?.tokens || {};
    for (const token of Object.values(tokens)) {
      if (token.type === "snail") {
        const { min } = bounds.value;
        const gridX = token.x - min;
        const gridY = token.y - min;
        map.set(`${gridX},${gridY}`, token);
      }
    }
    return map;
  });

  return { grid, snailPositions, bounds, gridSize };
}
