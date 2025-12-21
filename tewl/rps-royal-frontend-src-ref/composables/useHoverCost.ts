/**
 * useHoverCost - Shows cost indicator for hovered cell only
 *
 * Displays a colored overlay on the hovered cell:
 * - Blue for adjacent (free) moves
 * - Green for affordable jumps
 * - Red for unaffordable jumps
 */

import { watch, shallowRef, computed, type Ref } from "vue";
import * as THREE from "three";

// Colors
const ADJACENT_COLOR = 0x3b82f6; // Blue - free move
const AFFORDABLE_COLOR = 0x22c55e; // Green
const UNAFFORDABLE_COLOR = 0xef4444; // Red

interface HoverCostOptions {
  scene: Ref<THREE.Scene | null>;
  piecePosition: Ref<{ x: number; y: number } | null>;
  hoveredCell: Ref<{ x: number; y: number } | null>;
  energyBalance: Ref<number>;
}

export function useHoverCost({
  scene,
  piecePosition,
  hoveredCell,
  energyBalance,
}: HoverCostOptions) {
  const overlayGroup = shallowRef<THREE.Group | null>(null);

  // Check if adjacent (free move)
  const isAdjacent = computed(() => {
    if (!piecePosition.value || !hoveredCell.value) return false;
    const dx = Math.abs(hoveredCell.value.x - piecePosition.value.x);
    const dy = Math.abs(hoveredCell.value.y - piecePosition.value.y);
    return dx <= 1 && dy <= 1 && (dx + dy > 0);
  });

  // Calculate move cost (0 for adjacent/free moves)
  const moveCost = computed(() => {
    if (!piecePosition.value || !hoveredCell.value) return 0;
    if (isAdjacent.value) return 0; // Adjacent moves are free
    const dx = hoveredCell.value.x - piecePosition.value.x;
    const dy = hoveredCell.value.y - piecePosition.value.y;
    return dx * dx + dy * dy;
  });

  // Check if same cell
  const isSameCell = computed(() => {
    if (!piecePosition.value || !hoveredCell.value) return true;
    return piecePosition.value.x === hoveredCell.value.x && 
           piecePosition.value.y === hoveredCell.value.y;
  });

  // Can afford the move
  const canAfford = computed(() => {
    if (isAdjacent.value) return true;
    return energyBalance.value >= moveCost.value;
  });

  // Is it a jump move
  const isJump = computed(() => !isAdjacent.value && !isSameCell.value);

  function initGroup() {
    if (!scene.value) return;

    if (overlayGroup.value) {
      scene.value.remove(overlayGroup.value);
      disposeGroup(overlayGroup.value);
    }

    const group = new THREE.Group();
    group.name = "hoverCostGroup";
    scene.value.add(group);
    overlayGroup.value = group;
  }

  function disposeGroup(group: THREE.Group) {
    group.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.Sprite) {
        obj.geometry?.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else if (obj.material) {
          (obj.material as THREE.Material).dispose();
        }
      }
    });
  }

  function updateOverlay() {
    if (!overlayGroup.value) return;

    // Clear existing
    while (overlayGroup.value.children.length > 0) {
      const child = overlayGroup.value.children[0];
      overlayGroup.value.remove(child);
      if (child instanceof THREE.Mesh || child instanceof THREE.Sprite) {
        child.geometry?.dispose();
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else if (child.material) {
          (child.material as THREE.Material).dispose();
        }
      }
    }

    // Don't show if no piece selected or hovering same cell
    if (!piecePosition.value || !hoveredCell.value || isSameCell.value) {
      return;
    }

    const { x, y } = hoveredCell.value;

    // Determine color
    let color: number;
    let opacity: number;

    if (isAdjacent.value) {
      color = ADJACENT_COLOR;
      opacity = 0.35;
    } else if (canAfford.value) {
      color = AFFORDABLE_COLOR;
      opacity = 0.4;
    } else {
      color = UNAFFORDABLE_COLOR;
      opacity = 0.45;
    }

    // Create cell overlay (cost badge is on the arc now)
    const cellGeometry = new THREE.PlaneGeometry(0.95, 0.95);
    const cellMaterial = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      side: THREE.DoubleSide,
    });
    const cellMesh = new THREE.Mesh(cellGeometry, cellMaterial);
    cellMesh.rotation.x = -Math.PI / 2;
    cellMesh.position.set(x + 0.5, 0.025, y + 0.5);
    cellMesh.name = "hoverCostCell";
    overlayGroup.value.add(cellMesh);
  }

  // Watch for scene initialization
  watch(
    scene,
    (newScene) => {
      if (newScene) {
        initGroup();
      }
    },
    { immediate: true }
  );

  // Watch for changes
  watch(
    [piecePosition, hoveredCell, energyBalance],
    () => {
      updateOverlay();
    },
    { immediate: true }
  );

  return {
    moveCost,
    isAdjacent,
    isJump,
    canAfford,
    isSameCell,
  };
}

