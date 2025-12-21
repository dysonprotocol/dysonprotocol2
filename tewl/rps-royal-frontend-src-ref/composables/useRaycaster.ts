/**
 * useRaycaster - Handle tap/click detection for piece and cell selection
 *
 * Features:
 * - Convert screen coords to NDC
 * - Raycast against pieces first, then grid
 * - Mouse and touch support
 */

import { ref, watch, onUnmounted, type Ref } from "vue";
import * as THREE from "three";
import type { GameState } from "@/types/game";

export interface SelectionState {
  pieceId: string | number | null;
  cellX: number | null;
  cellY: number | null;
}

export function useRaycaster(
  camera: Ref<THREE.Camera | null>,
  scene: Ref<THREE.Scene | null>,
  domElement: Ref<HTMLElement | null>,
  gameState?: Ref<GameState | null>,
  playerAddress?: Ref<string | null>
) {
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  // Drag detection
  const pointerStartPos = { x: 0, y: 0 };
  const CLICK_THRESHOLD = 5; // pixels - if moved less than this, it's a click

  // Selection state
  const selectedPieceId = ref<string | number | null>(null);
  const hoveredCell = ref<{ x: number; y: number } | null>(null);
  const lastClickedCell = ref<{ x: number; y: number } | null>(null);

  function updatePointer(event: PointerEvent | TouchEvent) {
    if (!domElement.value) return;

    const rect = domElement.value.getBoundingClientRect();
    let clientX: number, clientY: number;

    if (event instanceof TouchEvent) {
      if (event.touches.length === 0) return;
      clientX = event.touches[0].clientX;
      clientY = event.touches[0].clientY;
    } else {
      clientX = event.clientX;
      clientY = event.clientY;
    }

    // Convert to normalized device coordinates (-1 to +1)
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  }

  function raycast(): THREE.Intersection[] {
    if (!camera.value || !scene.value) return [];

    raycaster.setFromCamera(pointer, camera.value);
    return raycaster.intersectObjects(scene.value.children, true);
  }

  function findPieceIntersection(intersections: THREE.Intersection[]): {
    pieceId: string | number;
    position: THREE.Vector3;
  } | null {
    for (const intersection of intersections) {
      // Check if we hit a clickTarget or any part of a piece group
      const objName = intersection.object.name;

      // Walk up the parent chain to find piece group
      let obj: THREE.Object3D | null = intersection.object;
      while (obj) {
        if (obj.name?.startsWith("piece-")) {
          const pieceId = obj.name.replace("piece-", "");
          console.log("[useRaycaster] Found piece:", pieceId, "via", objName);
          return { pieceId, position: obj.position.clone() };
        }
        obj = obj.parent;
      }
    }
    return null;
  }

  function findGridIntersection(intersections: THREE.Intersection[]): {
    x: number;
    y: number;
  } | null {
    // Look for cell mesh hits - these have names like "cell-5-3"
    for (const intersection of intersections) {
      const name = intersection.object.name;
      if (name.startsWith("cell-")) {
        const parts = name.split("-");
        if (parts.length === 3) {
          const x = parseInt(parts[1], 10);
          const y = parseInt(parts[2], 10);
          if (!isNaN(x) && !isNaN(y)) {
            return { x, y };
          }
        }
      }
    }

    // Fallback to ground plane (for areas outside cell meshes)
    for (const intersection of intersections) {
      if (
        intersection.object.name === "groundPlane" ||
        intersection.object.name === "cellHighlight"
      ) {
        const point = intersection.point;
        const cellX = Math.floor(point.x);
        const cellY = Math.floor(point.z);
        return { x: cellX, y: cellY };
      }
    }
    return null;
  }

  function onPointerDown(event: PointerEvent) {
    if (event.button !== 0) return;
    pointerStartPos.x = event.clientX;
    pointerStartPos.y = event.clientY;
  }

  function onPointerUp(event: PointerEvent) {
    if (event.button !== 0) return;

    // Check if this was a click (not a drag)
    const dx = event.clientX - pointerStartPos.x;
    const dy = event.clientY - pointerStartPos.y;
    if (Math.abs(dx) > CLICK_THRESHOLD || Math.abs(dy) > CLICK_THRESHOLD) {
      return; // Was a drag, not a click
    }

    updatePointer(event);
    const intersections = raycast();

    // Check for piece first
    const pieceHit = findPieceIntersection(intersections);
    if (pieceHit) {
      // Check ownership - only allow selecting own pieces
      if (gameState?.value && playerAddress?.value) {
        const token = gameState.value.tokens?.[String(pieceHit.pieceId)];
        if (token && token.owner !== playerAddress.value) {
          // Not owned by player - don't select, but allow clicking grid behind it
          const gridHit = findGridIntersection(intersections);
          if (gridHit) {
            lastClickedCell.value = gridHit;
          }
          return;
        }
      }

      // Toggle selection
      if (selectedPieceId.value === pieceHit.pieceId) {
        selectedPieceId.value = null;
      } else {
        selectedPieceId.value = pieceHit.pieceId;
      }
      return;
    }

    // Check for grid cell
    const gridHit = findGridIntersection(intersections);
    if (gridHit) {
      lastClickedCell.value = gridHit;
    }
  }

  function onPointerMove(event: PointerEvent) {
    updatePointer(event);
    const intersections = raycast();

    // Check for grid hover
    const gridHit = findGridIntersection(intersections);
    if (gridHit) {
      hoveredCell.value = gridHit;
    } else {
      hoveredCell.value = null;
    }
  }

  function onTouchStart(event: TouchEvent) {
    if (event.touches.length !== 1) return;

    updatePointer(event);
    const intersections = raycast();

    console.log(
      "[useRaycaster] Touch start, intersections:",
      intersections.length
    );

    // Same logic as pointer up
    const pieceHit = findPieceIntersection(intersections);
    if (pieceHit) {
      // Toggle selection
      if (selectedPieceId.value === pieceHit.pieceId) {
        selectedPieceId.value = null;
      } else {
        selectedPieceId.value = pieceHit.pieceId;
      }
      return;
    }

    const gridHit = findGridIntersection(intersections);
    if (gridHit) {
      lastClickedCell.value = gridHit;
    }
  }

  function clearSelection() {
    selectedPieceId.value = null;
  }

  // Setup event listeners
  function setupListeners() {
    if (!domElement.value) {
      console.warn("[useRaycaster] No DOM element for listeners");
      return;
    }

    domElement.value.addEventListener("pointerdown", onPointerDown);
    domElement.value.addEventListener("pointerup", onPointerUp);
    domElement.value.addEventListener("pointermove", onPointerMove);
    domElement.value.addEventListener("touchstart", onTouchStart, {
      passive: true,
    });
  }

  function removeListeners() {
    if (!domElement.value) return;
    domElement.value.removeEventListener("pointerdown", onPointerDown);
    domElement.value.removeEventListener("pointerup", onPointerUp);
    domElement.value.removeEventListener("pointermove", onPointerMove);
    domElement.value.removeEventListener("touchstart", onTouchStart);
  }

  // Watch for DOM element changes
  watch(
    domElement,
    (newElement, oldElement) => {
      if (oldElement) removeListeners();
      if (newElement) setupListeners();
    },
    { immediate: true }
  );

  onUnmounted(() => {
    removeListeners();
  });

  return {
    selectedPieceId,
    hoveredCell,
    lastClickedCell,
    clearSelection,
  };
}
