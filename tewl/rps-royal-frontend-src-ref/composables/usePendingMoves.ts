/**
 * usePendingMoves - Polls unconfirmed txs and extracts pending move_piece calls
 */
import { ref, computed, onUnmounted, type Ref } from "vue";
// @ts-expect-error dysonTxUtils is JS without type declarations
import { decodeTxRaw } from "@/utils/dysonTxUtils";
import { fromBase64 } from "@cosmjs/encoding";
import { SCRIPT_ADDRESS } from "@/types/game";

export interface PendingMove {
  pieceId: number;
  targetX: number;
  targetY: number;
  executor: string;
}

export function usePendingMoves(
  gameState: Ref<
    { tokens?: Record<string, { x: number; y: number }> } | null | undefined
  >,
  pollInterval = 500 // Poll frequently to catch new txs quickly
) {
  // What we display - adds quickly, removes only on sync
  const pendingMoves = ref<PendingMove[]>([]);
  // What's currently in the mempool (updated each poll)
  const mempoolSnapshot = ref<Set<string>>(new Set());
  const isPolling = ref(false);
  const lastError = ref<string | null>(null);
  let intervalId: ReturnType<typeof setInterval> | null = null;

  // Create a unique key for a pending move
  function moveKey(m: PendingMove): string {
    return `${m.pieceId}:${m.targetX},${m.targetY}:${m.executor}`;
  }

  async function fetchPendingTxs() {
    try {
      const resp = await fetch("/rpc/unconfirmed_txs?limit=100");
      if (!resp.ok) return;

      const data = await resp.json();
      const txs: string[] = data.result?.txs || [];

      const currentMoves: PendingMove[] = [];
      const currentKeys = new Set<string>();

      for (const txBase64 of txs) {
        try {
          const txBytes = fromBase64(txBase64);
          const decoded = decodeTxRaw(txBytes);

          // Check each message in the tx body
          for (const msg of decoded.body?.messages || []) {
            // msg is an Any type with typeUrl and value
            if (msg.typeUrl !== "/dysonprotocol.script.v1.MsgExec") continue;

            // Decode the MsgExec value
            const msgValue = decodeMsgExec(msg.value);
            if (!msgValue) continue;

            if (
              msgValue.scriptAddress !== SCRIPT_ADDRESS ||
              msgValue.functionName !== "move_piece"
            )
              continue;

            // Parse kwargs
            try {
              const kwargs = JSON.parse(msgValue.kwargs || "{}");
              const move: PendingMove = {
                pieceId: kwargs.piece_id,
                targetX: kwargs.target_x,
                targetY: kwargs.target_y,
                executor: msgValue.executorAddress,
              };
              currentMoves.push(move);
              currentKeys.add(moveKey(move));
            } catch {
              // Invalid kwargs JSON
            }
          }
        } catch {
          // Failed to decode tx
        }
      }

      // Update mempool snapshot
      mempoolSnapshot.value = currentKeys;

      // Merge: keep existing + add new (deduplicated by key)
      const mergedMap = new Map<string, PendingMove>();
      // Add existing first
      for (const move of pendingMoves.value) {
        mergedMap.set(moveKey(move), move);
      }
      // Add/update with current mempool moves
      for (const move of currentMoves) {
        mergedMap.set(moveKey(move), move);
      }
      pendingMoves.value = Array.from(mergedMap.values());

      lastError.value = null;
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : "Network error";
    }
  }

  // Call this when game state is fetched to remove confirmed txs
  async function syncRemovals() {
    // Fetch fresh mempool state before removing
    await fetchPendingTxs();
    // Remove moves that are no longer in the mempool
    pendingMoves.value = pendingMoves.value.filter((move) =>
      mempoolSnapshot.value.has(moveKey(move))
    );
  }

  // Simple MsgExec decoder - extracts fields from protobuf bytes
  function decodeMsgExec(value: Uint8Array): {
    executorAddress: string;
    scriptAddress: string;
    functionName: string;
    kwargs: string;
  } | null {
    try {
      // MsgExec protobuf structure:
      // field 1: executor_address (string)
      // field 2: script_address (string)
      // field 3: script_name (string)
      // field 4: extra_code (string)
      // field 5: function_name (string)
      // field 6: args (string)
      // field 7: kwargs (string)
      // field 8: attached_messages (repeated)

      const fields: Record<number, string> = {};
      let pos = 0;

      while (pos < value.length) {
        const tag = value[pos++];
        const fieldNum = tag >> 3;
        const wireType = tag & 0x7;

        if (wireType === 2) {
          // Length-delimited (string)
          let len = 0;
          let shift = 0;
          while (pos < value.length) {
            const b = value[pos++];
            len |= (b & 0x7f) << shift;
            if (!(b & 0x80)) break;
            shift += 7;
          }
          const strBytes = value.slice(pos, pos + len);
          fields[fieldNum] = new TextDecoder().decode(strBytes);
          pos += len;
        } else if (wireType === 0) {
          // Varint - skip
          while (pos < value.length && value[pos++] & 0x80) {}
        } else {
          break; // Unknown wire type
        }
      }

      return {
        executorAddress: fields[1] || "",
        scriptAddress: fields[2] || "",
        functionName: fields[5] || "",
        kwargs: fields[7] || "",
      };
    } catch {
      return null;
    }
  }

  function startPolling() {
    if (isPolling.value) return;
    isPolling.value = true;
    fetchPendingTxs();
    intervalId = setInterval(fetchPendingTxs, pollInterval);
  }

  function stopPolling() {
    isPolling.value = false;
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  }

  // Compute pending moves with source positions from game state
  const pendingMovesWithPositions = computed(() => {
    const tokens = gameState.value?.tokens;
    if (!tokens) return [];

    return pendingMoves.value
      .map((move) => {
        const piece = tokens[String(move.pieceId)];
        if (!piece) return null;
        return {
          ...move,
          fromX: piece.x,
          fromY: piece.y,
        };
      })
      .filter(Boolean) as Array<PendingMove & { fromX: number; fromY: number }>;
  });

  // Always start polling - we have a fallback to window.location.origin
  startPolling();

  onUnmounted(stopPolling);

  return {
    pendingMoves,
    pendingMovesWithPositions,
    isPolling,
    lastError,
    startPolling,
    stopPolling,
    refetch: fetchPendingTxs,
    syncRemovals,
  };
}
