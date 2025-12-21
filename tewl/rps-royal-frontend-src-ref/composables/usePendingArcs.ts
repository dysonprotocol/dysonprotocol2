/**
 * usePendingArcs - Renders blue arcs for pending move_piece transactions
 */
import { watch, shallowRef, type Ref } from "vue";
import * as THREE from "three";

const ARC_PENDING_COLOR = 0x3b82f6; // Blue

interface PendingMoveWithPosition {
  pieceId: number;
  fromX: number;
  fromY: number;
  targetX: number;
  targetY: number;
}

interface PendingArcsOptions {
  scene: Ref<THREE.Scene | null>;
  pendingMoves: Ref<PendingMoveWithPosition[]>;
}

export function usePendingArcs({ scene, pendingMoves }: PendingArcsOptions) {
  const arcGroup = shallowRef<THREE.Group | null>(null);

  function initGroup() {
    if (!scene.value) return;

    if (arcGroup.value) {
      scene.value.remove(arcGroup.value);
      disposeGroup(arcGroup.value);
    }

    const group = new THREE.Group();
    group.name = "pendingArcsGroup";
    scene.value.add(group);
    arcGroup.value = group;
  }

  function disposeGroup(group: THREE.Group) {
    group.traverse((obj) => {
      if (obj instanceof THREE.Line || obj instanceof THREE.Mesh) {
        obj.geometry?.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else if (obj.material) {
          (obj.material as THREE.Material).dispose();
        }
      }
    });
  }

  function renderArcs() {
    if (!arcGroup.value) return;

    // Clear existing arcs
    while (arcGroup.value.children.length > 0) {
      const child = arcGroup.value.children[0];
      arcGroup.value.remove(child);
      if (child instanceof THREE.Line || child instanceof THREE.Mesh) {
        child.geometry?.dispose();
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else if (child.material) {
          (child.material as THREE.Material).dispose();
        }
      }
    }

    for (const move of pendingMoves.value) {
      const from = { x: move.fromX, y: move.fromY };
      const to = { x: move.targetX, y: move.targetY };

      // Skip same cell
      if (from.x === to.x && from.y === to.y) continue;

      // Render arc for all moves (small arc for walks, big arc for jumps)
      renderArc(from, to);
    }
  }

  function renderArc(
    from: { x: number; y: number },
    to: { x: number; y: number }
  ) {
    if (!arcGroup.value) return;

    // Guard against undefined values
    if (from.x == null || from.y == null || to.x == null || to.y == null)
      return;

    const startX = from.x + 0.5;
    const startZ = from.y + 0.5;
    const endX = to.x + 0.5;
    const endZ = to.y + 0.5;

    const distance = Math.sqrt((endX - startX) ** 2 + (endZ - startZ) ** 2);

    // Skip if distance is too small (would cause curve issues)
    if (distance < 0.01) return;

    const radius = distance / 2;

    // Generate semi-circle arc points
    const numPoints = 32;
    const points: THREE.Vector3[] = [];

    for (let i = 0; i <= numPoints; i++) {
      const t = i / numPoints;
      const angle = Math.PI * t;

      const linearX = startX + (endX - startX) * t;
      const linearZ = startZ + (endZ - startZ) * t;
      const y = Math.sin(angle) * radius + 0.3;

      points.push(new THREE.Vector3(linearX, y, linearZ));
    }

    // Create tube arc
    const curve = new THREE.CatmullRomCurve3(points);
    const tubeGeometry = new THREE.TubeGeometry(curve, 32, 0.05, 8, false);
    const tubeMaterial = new THREE.MeshBasicMaterial({
      color: ARC_PENDING_COLOR,
      transparent: true,
      opacity: 0.7,
    });
    const arcTube = new THREE.Mesh(tubeGeometry, tubeMaterial);
    arcTube.name = "pendingArcTube";
    arcGroup.value.add(arcTube);

    // Add dashed trail
    const dashMaterial = new THREE.LineDashedMaterial({
      color: 0xffffff,
      linewidth: 1,
      dashSize: 0.15,
      gapSize: 0.1,
      transparent: true,
      opacity: 0.3,
    });
    const dashGeometry = new THREE.BufferGeometry().setFromPoints(points);
    const dashLine = new THREE.Line(dashGeometry, dashMaterial);
    dashLine.computeLineDistances();
    dashLine.name = "pendingArcDash";
    arcGroup.value.add(dashLine);

    // Add blue square at destination (90% of cell size)
    const squareGeometry = new THREE.PlaneGeometry(0.9, 0.9);
    const squareMaterial = new THREE.MeshBasicMaterial({
      color: ARC_PENDING_COLOR,
      transparent: true,
      opacity: 0.8,
      side: THREE.DoubleSide,
    });
    const square = new THREE.Mesh(squareGeometry, squareMaterial);
    square.rotation.x = -Math.PI / 2; // Lay flat on the ground
    square.position.set(endX, 0.01, endZ); // Flat with grid
    square.name = "pendingDestSquare";
    arcGroup.value.add(square);
  }

  // Watch for scene initialization
  watch(
    scene,
    (newScene) => {
      if (newScene) {
        initGroup();
        renderArcs();
      }
    },
    { immediate: true }
  );

  // Watch for pending moves changes
  watch(pendingMoves, renderArcs, { deep: true });

  return { renderArcs };
}
