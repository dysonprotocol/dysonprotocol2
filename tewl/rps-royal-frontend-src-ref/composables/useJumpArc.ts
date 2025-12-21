/**
 * useMoveArc - Renders a parabolic arc for all moves
 *
 * Shows a curved trajectory from piece to target cell
 * with cost badge showing energy cost or "Free" for walks
 */

import { watch, shallowRef, type Ref } from "vue";
import * as THREE from "three";

// Arc colors
const ARC_AFFORDABLE_COLOR = 0x22c55e; // Green
const ARC_UNAFFORDABLE_COLOR = 0xef4444; // Red

interface JumpArcOptions {
  scene: Ref<THREE.Scene | null>;
  piecePosition: Ref<{ x: number; y: number } | null>;
  targetPosition: Ref<{ x: number; y: number } | null>;
  canAfford: Ref<boolean>;
  moveCost: Ref<number>;
}

export function useJumpArc({
  scene,
  piecePosition,
  targetPosition,
  canAfford,
  moveCost,
}: JumpArcOptions) {
  const arcGroup = shallowRef<THREE.Group | null>(null);
  const isVisible = shallowRef(false);

  function initGroup() {
    if (!scene.value) return;

    // Remove existing group
    if (arcGroup.value) {
      scene.value.remove(arcGroup.value);
      disposeGroup(arcGroup.value);
    }

    const group = new THREE.Group();
    group.name = "jumpArcGroup";
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

  function showArc() {
    if (!arcGroup.value || !piecePosition.value || !targetPosition.value) {
      clearArc();
      return;
    }

    const from = piecePosition.value;
    const to = targetPosition.value;

    // Don't show arc for same cell
    if (from.x === to.x && from.y === to.y) {
      clearArc();
      return;
    }

    // Clear existing arc
    clearArc();

    const color = canAfford.value
      ? ARC_AFFORDABLE_COLOR
      : ARC_UNAFFORDABLE_COLOR;

    // Calculate arc points
    const startX = from.x + 0.5;
    const startZ = from.y + 0.5;
    const endX = to.x + 0.5;
    const endZ = to.y + 0.5;

    // Calculate distance and arc parameters
    const distance = Math.sqrt((endX - startX) ** 2 + (endZ - startZ) ** 2);
    const radius = distance / 2; // Semi-circle radius
    const arcHeight = radius; // Peak height equals radius for semi-circle

    // Generate semi-circle arc points
    const numPoints = 32;
    const points: THREE.Vector3[] = [];

    // Center point between start and end
    const centerX = (startX + endX) / 2;
    const centerZ = (startZ + endZ) / 2;

    // Direction from start to end (normalized)
    const dirX = (endX - startX) / distance;
    const dirZ = (endZ - startZ) / distance;

    for (let i = 0; i <= numPoints; i++) {
      const t = i / numPoints;
      const angle = Math.PI * t; // 0 to PI for semi-circle

      // Position along the line from start to end
      const linearX = startX + (endX - startX) * t;
      const linearZ = startZ + (endZ - startZ) * t;

      // Height follows semi-circle: sin(angle) * radius
      const y = Math.sin(angle) * radius + 0.3;

      points.push(new THREE.Vector3(linearX, y, linearZ));
    }

    // Create thick arc using TubeGeometry for visibility
    const curve = new THREE.CatmullRomCurve3(points);
    const tubeGeometry = new THREE.TubeGeometry(curve, 32, 0.06, 8, false);
    const tubeMaterial = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.85,
    });
    const arcTube = new THREE.Mesh(tubeGeometry, tubeMaterial);
    arcTube.name = "jumpArcTube";
    arcGroup.value.add(arcTube);

    // Add thin dashed trail effect
    const dashMaterial = new THREE.LineDashedMaterial({
      color: 0xffffff,
      linewidth: 1,
      dashSize: 0.15,
      gapSize: 0.1,
      transparent: true,
      opacity: 0.4,
    });
    const dashGeometry = new THREE.BufferGeometry().setFromPoints(points);
    const dashLine = new THREE.Line(dashGeometry, dashMaterial);
    dashLine.computeLineDistances();
    dashLine.name = "jumpArcDash";
    arcGroup.value.add(dashLine);

    // Add circle rings at piece and target positions
    const ringGeometry = new THREE.RingGeometry(0.35, 0.45, 32);
    const ringMaterial = new THREE.MeshBasicMaterial({
      color,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.8,
    });

    // Start ring (piece position)
    const startRing = new THREE.Mesh(ringGeometry, ringMaterial);
    startRing.rotation.x = -Math.PI / 2; // Lay flat
    startRing.position.set(startX, 0.02, startZ);
    startRing.name = "startRing";
    arcGroup.value.add(startRing);

    // End ring (target position)
    const endRing = new THREE.Mesh(ringGeometry.clone(), ringMaterial.clone());
    endRing.rotation.x = -Math.PI / 2;
    endRing.position.set(endX, 0.02, endZ);
    endRing.name = "endRing";
    arcGroup.value.add(endRing);

    // Add cost badge at peak of arc (only for non-free moves)
    const cost = moveCost.value;
    if (cost > 0) {
      const peakX = (startX + endX) / 2;
      const peakY = arcHeight + 0.7; // Slightly above the arc peak (radius + offset)
      const peakZ = (startZ + endZ) / 2;

      const costSprite = createCostSprite(cost, canAfford.value);
      costSprite.position.set(peakX, peakY, peakZ);
      arcGroup.value.add(costSprite);
    }

    isVisible.value = true;
  }

  function createCostSprite(cost: number, affordable: boolean): THREE.Sprite {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 64;
    const ctx = canvas.getContext("2d")!;

    ctx.clearRect(0, 0, 128, 64);

    const isFree = cost === 0;

    // Background pill (always green for free moves)
    ctx.fillStyle =
      isFree || affordable
        ? "rgba(34, 197, 94, 0.95)"
        : "rgba(239, 68, 68, 0.95)";
    ctx.beginPath();
    ctx.roundRect(8, 8, 112, 48, 12);
    ctx.fill();

    // Border
    ctx.strokeStyle =
      isFree || affordable ? "rgba(22, 163, 74, 1)" : "rgba(185, 28, 28, 1)";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Cost text
    ctx.font = "bold 26px Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "white";
    ctx.fillText(isFree ? "Free" : `${cost}⚡`, 64, 32);

    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;

    const spriteMaterial = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false,
      sizeAttenuation: false, // Scale-invariant: same screen size regardless of distance
    });
    const sprite = new THREE.Sprite(spriteMaterial);
    sprite.scale.set(0.055, 0.028, 1); // Smaller values for screen-space sizing
    sprite.name = "costSprite";

    return sprite;
  }

  function clearArc() {
    if (!arcGroup.value) return;

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

    isVisible.value = false;
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

  // Watch for position/affordability/cost changes
  watch(
    [piecePosition, targetPosition, canAfford, moveCost],
    () => {
      showArc();
    },
    { immediate: true }
  );

  return {
    showArc,
    clearArc,
    isVisible,
  };
}
