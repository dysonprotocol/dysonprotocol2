<script setup lang="ts">
import { ref, computed, toRef, watch, onMounted, onUnmounted } from "vue";
import { RouterLink } from "vue-router";
import { toast } from "vue-sonner";
import { useWallet } from "@/composables/useWallet";
import {
  useGameState,
  useOwnedTokens,
  useBalance,
  useEnergyBalance,
  useSpawnMutation,
  useMoveMutation,
  useGrid,
} from "@/composables/useRpsGame";
import { useThreeScene } from "@/composables/useThreeScene";
import { useGridRenderer } from "@/composables/useGridRenderer";
import { usePieceRenderer } from "@/composables/usePieceRenderer";
import { useRaycaster } from "@/composables/useRaycaster";
import { useJumpArc } from "@/composables/useJumpArc";
import { useHoverCost } from "@/composables/useHoverCost";
import { useBalanceWarnings } from "@/composables/useBalanceWarnings";
import { usePendingMoves } from "@/composables/usePendingMoves";
import { usePendingArcs } from "@/composables/usePendingArcs";
import { useCameraControls } from "@/composables/useCameraControls";
import { usePieceAnimations } from "@/composables/usePieceAnimations";
import { useEnergyCollection } from "@/composables/useEnergyCollection";
import AppSidebar from "@/components/game/AppSidebar.vue";
import SiteHeader from "@/components/game/SiteHeader.vue";
import MobileSpawnBar from "@/components/game/MobileSpawnBar.vue";
import LeaderboardSidebar from "@/components/game/LeaderboardSidebar.vue";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { type Token, type TokenTypeName } from "@/types/game";

// Wallet
const { wallet, openWalletDialog, signOut } = useWallet();
const justCopied = ref(false);
const address = computed(() => wallet.value?.address || null);

// Game state
const {
  data: gameState,
  isLoading: isLoadingGame,
  error: gameError,
} = useGameState();
const { data: ownedTokens } = useOwnedTokens(toRef(() => address.value));
const { data: balance } = useBalance(toRef(() => address.value));
const { data: energyBalance } = useEnergyBalance(toRef(() => address.value));
const { bounds, gridSize } = useGrid(
  toRef(() => gameState.value),
  toRef(() => address.value)
);

// Mutations
const spawnMutation = useSpawnMutation();
const moveMutation = useMoveMutation();

// UI state
const selectedToken = ref<Token | null>(null);

// Three.js
const threeContainer = ref<HTMLElement | null>(null);
const {
  scene,
  camera,
  renderer,
  isInitialized: isThreeReady,
} = useThreeScene(threeContainer);

// Grid bounds for camera limits and grid rendering
const gridBounds = computed(() => bounds.value || { min: -10, max: 10 });

// Grid renderer
const { gridGroup, highlightCell, clearHighlight } = useGridRenderer(
  scene,
  gridBounds
);

// Raycaster - handles selection (only own pieces)
const { selectedPieceId, hoveredCell, lastClickedCell, clearSelection } =
  useRaycaster(
    camera,
    scene,
    threeContainer,
    toRef(() => gameState.value),
    toRef(() => address.value)
  );

// Camera controls (AoE style - fixed angle, pan + zoom)
// Pass hoveredCell so edge scrolling only works when mouse is over grid
const { panToPiece, resetCamera } = useCameraControls(
  camera,
  renderer,
  scene,
  gridBounds,
  hoveredCell
);

// Piece renderer - renders tokens on grid (needs selectedPieceId for selection indicator)
const { pieces, getPieceAt } = usePieceRenderer(
  scene,
  toRef(() => gameState.value),
  toRef(() => address.value),
  selectedPieceId
);

// Piece animations
const { selectPop, deselect, startIdleBob, stopIdleBob } = usePieceAnimations();

// Energy collection effects
const { playCollectionEffect } = useEnergyCollection(scene);

// Energy balance as number
const energyBalanceNum = computed(() =>
  parseInt(energyBalance.value || "0", 10)
);

// Selected piece position
const selectedPiecePosition = computed(() => {
  if (!selectedPieceId.value || !gameState.value?.tokens) return null;
  const token = gameState.value.tokens[String(selectedPieceId.value)];
  return token ? { x: token.x, y: token.y } : null;
});

// Hover cost - shows cost for hovered cell only
const { moveCost, isAdjacent, isJump, canAfford } = useHoverCost({
  scene,
  piecePosition: selectedPiecePosition,
  hoveredCell,
  energyBalance: energyBalanceNum,
});

// Jump arc - shows parabolic arc for jump moves with cost at peak
useJumpArc({
  scene,
  piecePosition: selectedPiecePosition,
  targetPosition: hoveredCell,
  canAfford,
  moveCost,
});

// Pending moves from mempool - shows blue arcs for unconfirmed txs
const {
  pendingMovesWithPositions,
  isPolling: isMempoolPolling,
  lastError: mempoolError,
  syncRemovals,
} = usePendingMoves(toRef(() => gameState.value));
usePendingArcs({
  scene,
  pendingMoves: pendingMovesWithPositions,
});

// Sync pending move removals when game state updates
watch(gameState, () => {
  syncRemovals();
});

// Balance warnings
const { warningState, hasWarning, isCritical, isEmpty } =
  useBalanceWarnings(energyBalanceNum);

// Watch for cell hover to highlight
watch(hoveredCell, (cell) => {
  if (cell) {
    highlightCell(cell.x, cell.y);
  } else {
    clearHighlight();
  }
});

// Check if target cell has snail (from current game state)
function targetHasSnail(x: number, y: number): boolean {
  const tokens = gameState.value?.tokens || {};
  for (const token of Object.values(tokens)) {
    if (token.x === x && token.y === y && token.type === "snail") {
      return true;
    }
  }
  return false;
}

// Parse move error for better UX
function parseMoveError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes("target cell occupied by npc")) {
    return "🐌 The snail moved there! Try another cell.";
  }
  if (msg.includes("target cell occupied by ally")) {
    return "Your own piece is there!";
  }
  if (msg.includes("target cell occupied by same piece")) {
    return "Already at that position!";
  }
  return msg;
}

// Watch for cell clicks when a piece is selected
watch(lastClickedCell, async (cell) => {
  if (!cell || selectedPieceId.value === null) return;
  if (!wallet.value?.address) {
    toast.error("Connect wallet first");
    return;
  }

  const pieceId = Number(selectedPieceId.value);
  const piece = gameState.value?.tokens?.[String(pieceId)];
  if (!piece) return;
  if (piece.x === cell.x && piece.y === cell.y) return;

  // Check if snail is at target (best effort - snail might have moved)
  if (targetHasSnail(cell.x, cell.y)) {
    toast.error("🐌 Can't move to the snail's position!");
    return;
  }

  const dx = cell.x - piece.x;
  const dy = cell.y - piece.y;
  const cost = dx * dx + dy * dy;
  const adjacent = Math.abs(dx) <= 1 && Math.abs(dy) <= 1;

  // Check if can afford (adjacent moves are free)
  if (!adjacent && cost > energyBalanceNum.value) {
    toast.error(
      `Not enough energy! Need ${cost}⚡, have ${energyBalanceNum.value}⚡`
    );
    return;
  }

  console.log(
    "[GameView] Move:",
    pieceId,
    "->",
    cell.x,
    cell.y,
    adjacent ? "(walk)" : `(jump, ${cost}⚡)`
  );

  try {
    const result = await moveMutation.mutateAsync({
      pieceId,
      targetX: cell.x,
      targetY: cell.y,
    });

    // Check if energy was collected
    const scriptResponse = result.scriptResponse;
    if (scriptResponse?.status === "collected") {
      const amount = (scriptResponse.energy_gained as number) || 25;

      // Particles burst from energy location (target cell) and absorb into piece
      // Since piece is now at target, effect bursts outward then spirals back in
      playCollectionEffect(cell.x, cell.y, cell.x, cell.y);

      // Gold-themed toast for collection
      toast.success(`+${amount} ⚡ collected!`, {
        style: {
          background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
          border: "1px solid #ffd700",
          color: "#ffd700",
        },
      });
    } else if (adjacent) {
      toast.success(`Moved to (${cell.x}, ${cell.y})`);
    } else {
      toast.success(`Jumped to (${cell.x}, ${cell.y}) · ${cost}⚡`);
    }
  } catch (err) {
    toast.error(`Move failed: ${parseMoveError(err)}`);
  }
});

// Handle piece selection animations
watch(selectedPieceId, (newId, oldId) => {
  // Deselect animation for old piece
  if (oldId) {
    const sprite = pieces.value.get(String(oldId));
    if (sprite) {
      deselect(sprite.group);
    }
  }

  // Select animation for new piece
  if (newId && gameState.value?.tokens) {
    const token = gameState.value.tokens[String(newId)];
    if (token) {
      const sprite = pieces.value.get(String(newId));
      if (sprite) {
        selectPop(sprite.group);
      }
    }
  }
});

// Handlers
async function handleSpawn(tokenType: TokenTypeName) {
  console.log("[GameView] handleSpawn called with tokenType:", tokenType);
  try {
    const result = await spawnMutation.mutateAsync({ tokenType });
    console.log("[GameView] handleSpawn result:", result);
    toast.success("Piece spawned!");
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error("[GameView] handleSpawn error:", error);
    toast.error("Spawn failed: " + message);
  }
}

// Energy buy/sell is handled directly by EnergyMarket.vue using useEnergySwap

function handleSelectPieceFromList(pieceId: string | number) {
  // Find the piece and update selection
  const token = gameState.value?.tokens?.[String(pieceId)];
  if (token) {
    selectedPieceId.value = String(pieceId);
    // Pan camera to the piece
    panToPiece(token.x, token.y);
    console.log("[GameView] Selected piece from list:", pieceId, token);
  }
}

/** Returns true if user is focused on a form input (should ignore game keys) */
function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    (el as HTMLElement).isContentEditable
  );
}

// Keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  // Skip if typing in input field
  if (isInputFocused()) return;

  // Escape deselects
  if (e.key === "Escape") {
    selectedPieceId.value = null;
    return;
  }

  // Number keys 1-9 select piece by index
  const num = parseInt(e.key);
  if (num >= 1 && num <= 9) {
    const tokens = ownedTokens.value;
    if (tokens && num <= tokens.length) {
      const piece = tokens[num - 1];
      selectedPieceId.value = String(piece.id);
      panToPiece(piece.x, piece.y);
    }
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeyDown);
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeyDown);
});

// Computed
const formattedBalance = computed(() => {
  if (!balance.value) return "0";
  const n = BigInt(balance.value);
  return (Number(n) / 1e6).toFixed(2); // udys has 6 decimals
});

const formattedEnergyBalance = computed(() => energyBalance.value || "0");

const tokenCount = computed(() => ownedTokens.value?.length || 0);
const tick = computed(() => gameState.value?.state?.last_updated_block || 0);
const totalPieces = computed(() => gameState.value?.state?.total_pieces || 0);
const isGameInitialized = computed(() => gameState.value?.config !== null);

async function copyAddress() {
  if (!address.value) return;
  await navigator.clipboard.writeText(address.value);
  justCopied.value = true;
  toast.success("Address copied");
  setTimeout(() => {
    justCopied.value = false;
  }, 1500);
}

// Debug watchers
watch(
  gameState,
  (newState) => {
    console.log(
      "[GameView] gameState changed:",
      JSON.stringify(newState, null, 2)
    );
  },
  { deep: true }
);

watch(isThreeReady, (ready) => {
  console.log("[GameView] Three.js ready:", ready);
  if (ready && scene.value) {
    console.log("[GameView] Scene children:", scene.value.children.length);
  }
});

watch(gridGroup, (group) => {
  console.log(
    "[GameView] Grid group updated:",
    group ? group.children.length + " children" : "null"
  );
});
</script>

<template>
  <SidebarProvider class="h-full">
    <AppSidebar
      :address="address"
      :dys-balance="formattedBalance"
      :energy-balance="formattedEnergyBalance"
      :just-copied="justCopied"
      :tick="tick"
      :total-pieces="totalPieces"
      :grid-size="gridSize"
      :owned-pieces="ownedTokens"
      :selected-piece-id="selectedPieceId"
      :is-spawning="spawnMutation.isPending.value"
      :pending-moves="pendingMovesWithPositions"
      :is-mempool-polling="isMempoolPolling"
      :mempool-error="mempoolError"
      :has-warning="hasWarning"
      :is-critical="isCritical"
      :is-empty="isEmpty"
      :warning-message="warningState.message"
      @connect="openWalletDialog"
      @disconnect="signOut"
      @copy-address="copyAddress"
      @select-piece="handleSelectPieceFromList"
      @spawn="handleSpawn"
    />
    <SidebarInset class="flex flex-col">
      <SiteHeader
        :address="address"
        :energy-balance="formattedEnergyBalance"
        :has-warning="hasWarning"
        :is-critical="isCritical"
        :is-empty="isEmpty"
        @connect="openWalletDialog"
      />
      <!-- Main game area (pb-20 on mobile for spawn bar, pb-4 on desktop for floating bar) -->
      <main class="flex-1 relative overflow-hidden bg-background pb-20 md:pb-4">
        <!-- Loading state -->
        <div
          v-if="isLoadingGame"
          class="absolute inset-0 flex items-center justify-center"
        >
          <div class="text-muted-foreground animate-pulse">
            Loading game state...
          </div>
        </div>

        <!-- Error state -->
        <div
          v-else-if="gameError"
          class="absolute inset-0 flex items-center justify-center"
        >
          <div class="text-destructive text-center">
            <p>Failed to load game</p>
            <p class="text-sm text-muted-foreground">
              {{ (gameError as Error).message }}
            </p>
            <RouterLink
              to="/deploy"
              class="text-sm text-primary hover:underline mt-2 inline-block"
            >
              Go to Deploy Page →
            </RouterLink>
          </div>
        </div>

        <!-- Not initialized -->
        <div
          v-else-if="!isGameInitialized"
          class="absolute inset-0 flex items-center justify-center"
        >
          <div class="text-center space-y-3">
            <p class="text-lg">Game not initialized</p>
            <p class="text-sm text-muted-foreground">
              Deploy and initialize the script first
            </p>
            <RouterLink to="/deploy">
              <Button>Go to Deploy Page</Button>
            </RouterLink>
          </div>
        </div>

        <!-- Three.js Canvas Container -->
        <div v-else ref="threeContainer" class="absolute inset-0 touch-none" />
      </main>
    </SidebarInset>

    <!-- Leaderboard (right sidebar, desktop only) -->
    <LeaderboardSidebar :current-address="address" />

    <!-- Spawn bar (mobile: full width | desktop: centered floating) -->
    <MobileSpawnBar
      :owned-pieces="ownedTokens"
      :energy-balance="energyBalanceNum"
      :is-spawning="spawnMutation.isPending.value"
      :is-connected="!!address"
      @spawn="handleSpawn"
      @connect="openWalletDialog"
    />
  </SidebarProvider>
</template>
