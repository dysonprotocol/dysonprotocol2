/**
 * useGridRenderer - Renders the game grid as a 3D plane
 *
 * Features:
 * - Dynamic grid size based on game bounds
 * - Parchment-colored cells with grid lines
 * - Cell highlighting for hover/selection
 */

import { watch, shallowRef, type Ref } from "vue";
import * as THREE from "three";

// Grid colors (black ground with white lines)
const GRID_BASE_COLOR = 0x000000; // Black ground
const GRID_LINE_COLOR = 0xffffff; // White lines
const HIGHLIGHT_COLOR = 0x87ceeb; // Sky blue highlight

export interface GridBounds {
  min: number;
  max: number;
}

export function useGridRenderer(
  scene: Ref<THREE.Scene | null>,
  bounds: Ref<GridBounds>
) {
  const gridGroup = shallowRef<THREE.Group | null>(null);
  const highlightMesh = shallowRef<THREE.Mesh | null>(null);

  let currentHighlight: { x: number; y: number } | null = null;

  function createGrid() {
    if (!scene.value) {
      console.warn("[useGridRenderer] No scene, skipping grid creation");
      return;
    }

    // Remove existing grid
    if (gridGroup.value) {
      scene.value.remove(gridGroup.value);
      gridGroup.value.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else {
            obj.material?.dispose();
          }
        }
      });
    }

    const { min, max } = bounds.value;
    const gridSize = max - min + 1;
    const cellSize = 1;
    const totalSize = gridSize * cellSize;

    // Grid center in world coordinates (center of all cells)
    const centerX = (min + max + 1) / 2;
    const centerZ = (min + max + 1) / 2;

    const group = new THREE.Group();
    group.name = "gameGrid";

    // Main ground plane - centered on grid
    const groundGeometry = new THREE.PlaneGeometry(totalSize, totalSize);
    const groundMaterial = new THREE.MeshBasicMaterial({
      color: GRID_BASE_COLOR,
    });
    const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(centerX, 0, centerZ);
    ground.name = "groundPlane";
    group.add(ground);

    // Grid lines using LineSegments for better performance
    const linesMaterial = new THREE.LineBasicMaterial({
      color: GRID_LINE_COLOR,
      transparent: false,
    });

    const linesGeometry = new THREE.BufferGeometry();
    const linePoints: number[] = [];

    // Vertical lines
    for (let i = 0; i <= gridSize; i++) {
      const x = min + i;
      linePoints.push(x, 0.01, min);
      linePoints.push(x, 0.01, max + 1);
    }

    // Horizontal lines
    for (let i = 0; i <= gridSize; i++) {
      const z = min + i;
      linePoints.push(min, 0.01, z);
      linePoints.push(max + 1, 0.01, z);
    }

    linesGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(linePoints, 3)
    );
    const gridLines = new THREE.LineSegments(linesGeometry, linesMaterial);
    gridLines.name = "gridLines";
    group.add(gridLines);

    // Create individual cell meshes for accurate raycasting
    // Each cell is a separate mesh named "cell-X-Y" for direct coordinate extraction
    const cellGeometry = new THREE.PlaneGeometry(cellSize, cellSize);
    const cellMaterial = new THREE.MeshBasicMaterial({
      visible: false, // Invisible but raycastable
    });

    const cellsGroup = new THREE.Group();
    cellsGroup.name = "cellsGroup";

    for (let x = min; x <= max; x++) {
      for (let z = min; z <= max; z++) {
        const cellMesh = new THREE.Mesh(cellGeometry, cellMaterial);
        cellMesh.rotation.x = -Math.PI / 2;
        cellMesh.position.set(x + 0.5, 0.01, z + 0.5); // Center of cell, just above ground
        cellMesh.name = `cell-${x}-${z}`;
        cellsGroup.add(cellMesh);
      }
    }
    group.add(cellsGroup);

    // Highlight mesh (hidden by default)
    const highlightGeometry = new THREE.PlaneGeometry(
      cellSize * 0.95,
      cellSize * 0.95
    );
    const highlightMaterial = new THREE.MeshBasicMaterial({
      color: HIGHLIGHT_COLOR,
      transparent: true,
      opacity: 0.5,
    });
    const highlight = new THREE.Mesh(highlightGeometry, highlightMaterial);
    highlight.rotation.x = -Math.PI / 2;
    highlight.position.set(0, 0.03, 0);
    highlight.visible = false; // Start hidden
    highlight.name = "cellHighlight";
    group.add(highlight);
    highlightMesh.value = highlight;

    scene.value.add(group);
    gridGroup.value = group;
  }

  function highlightCell(worldX: number, worldY: number) {
    if (!highlightMesh.value) return;

    // Convert world coords to cell center
    const cellX = Math.floor(worldX) + 0.5;
    const cellZ = Math.floor(worldY) + 0.5;

    highlightMesh.value.position.set(cellX, 0.03, cellZ);
    highlightMesh.value.visible = true;
    currentHighlight = { x: worldX, y: worldY };
  }

  function clearHighlight() {
    if (!highlightMesh.value) return;

    highlightMesh.value.visible = false;
    currentHighlight = null;
  }

  function worldToCell(
    worldX: number,
    worldZ: number
  ): { x: number; y: number } {
    return {
      x: Math.floor(worldX),
      y: Math.floor(worldZ),
    };
  }

  function cellToWorld(cellX: number, cellY: number): { x: number; z: number } {
    return {
      x: cellX + 0.5,
      z: cellY + 0.5,
    };
  }

  watch(
    [scene, bounds],
    ([newScene]) => {
      if (newScene) createGrid();
    },
    { immediate: true }
  );

  return {
    gridGroup,
    highlightCell,
    clearHighlight,
    worldToCell,
    cellToWorld,
    createGrid,
  };
}
