/**
 * usePieceRenderer - Renders game pieces as billboard sprites
 *
 * Paper Mario style: flat sprites with emoji icons
 * Features:
 * - Rock 🪨 / Paper 📄 / Scissors ✂️ / Snail 🐌 / Energy ⚡ icons
 * - Ownership indicators: outline (green=player, red=enemy, purple=snail)
 * - Selected piece shown with filled square, unselected with outline only
 */

import { watch, shallowRef, onUnmounted, type Ref } from "vue";
import * as THREE from "three";
import type { Token, GameState } from "@/types/game";

// Piece emojis
const PIECE_EMOJIS: Record<string, string> = {
  rock: "🪨",
  paper: "📄",
  scissors: "✂️",
  snail: "🐌",
  energy: "⚡",
};

// Ownership ring colors
const OWNERSHIP_COLORS = {
  player: 0x2ecc71, // Green
  enemy: 0xe74c3c, // Red
  snail: 0x9b59b6, // Purple
  energy: 0xffd700, // Gold
  selected: 0x3b82f6, // Blue
};

// Piece dimensions
const PIECE_SIZE = 0.8;
const SNAIL_SIZE = 1.0;

// Cache for emoji textures
const textureCache = new Map<string, THREE.CanvasTexture>();

function createEmojiTexture(
  emoji: string,
  size: number = 128
): THREE.CanvasTexture {
  const cacheKey = `${emoji}-${size}`;
  if (textureCache.has(cacheKey)) {
    return textureCache.get(cacheKey)!;
  }

  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;

  // Clear with transparency
  ctx.clearRect(0, 0, size, size);

  // Draw emoji centered
  ctx.font = `${size * 0.75}px serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, size / 2, size / 2 + size * 0.05);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  textureCache.set(cacheKey, texture);

  return texture;
}

export interface PieceSprite {
  group: THREE.Group;
  mesh: THREE.Mesh;
  ring: THREE.Mesh;
  tokenId: number | string;
  targetX: number;
  targetZ: number;
  // Animation state
  animating: boolean;
  animStartX: number;
  animStartZ: number;
  animProgress: number;
  animDistance: number;
  trailParticles: THREE.Mesh[];
}

export function usePieceRenderer(
  scene: Ref<THREE.Scene | null>,
  gameState: Ref<GameState | null>,
  playerAddress: Ref<string | null>,
  selectedPieceId?: Ref<string | number | null>
) {
  const pieces = shallowRef<Map<string | number, PieceSprite>>(new Map());
  const piecesGroup = shallowRef<THREE.Group | null>(null);

  // Create piece geometry and materials (reused)
  const pieceGeometry = new THREE.PlaneGeometry(PIECE_SIZE, PIECE_SIZE);
  const snailGeometry = new THREE.PlaneGeometry(SNAIL_SIZE, SNAIL_SIZE);
  // Filled square geometry for ownership indicator
  const filledSquareGeometry = new THREE.PlaneGeometry(0.9, 0.9);

  function createPieceMaterial(type: string): THREE.MeshBasicMaterial {
    const emoji = PIECE_EMOJIS[type] || "❓";
    const texture = createEmojiTexture(emoji);
    return new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.DoubleSide,
      transparent: true,
    });
  }

  function getRingColor(owner: string, pieceType: string): number {
    if (pieceType === "snail") return OWNERSHIP_COLORS.snail;
    if (pieceType === "energy") return OWNERSHIP_COLORS.energy;
    if (playerAddress.value && owner === playerAddress.value)
      return OWNERSHIP_COLORS.player;
    return OWNERSHIP_COLORS.enemy;
  }

  function createPieceSprite(token: Token): PieceSprite {
    const isSnail = token.type === "snail";
    const group = new THREE.Group();
    group.name = `piece-${token.id}`;

    // Main piece mesh (billboard with emoji texture)
    const geometry = isSnail ? snailGeometry : pieceGeometry;
    const material = createPieceMaterial(token.type);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 4; // Slight tilt for Paper Mario look
    mesh.position.y = isSnail ? SNAIL_SIZE / 2 + 0.05 : PIECE_SIZE / 2 + 0.05;
    mesh.name = "pieceMesh";
    mesh.raycast = () => {}; // Disable raycasting - use clickTarget instead
    group.add(mesh);

    // Ownership square (on ground) - filled square
    const ringColor = getRingColor(token.owner, token.type);
    const ringMaterial = new THREE.MeshBasicMaterial({
      color: ringColor,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.6,
    });
    const ring = new THREE.Mesh(filledSquareGeometry, ringMaterial);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02; // Flat with grid
    ring.name = "ownerRing";
    ring.raycast = () => {}; // Disable raycasting - use clickTarget instead
    group.add(ring);

    // Invisible click target (larger area for easier selection)
    // Position above cell meshes (which are at y=0.01) so it gets hit first
    const clickTargetGeometry = new THREE.PlaneGeometry(0.9, 0.9);
    const clickTargetMaterial = new THREE.MeshBasicMaterial({
      visible: false,
    });
    const clickTarget = new THREE.Mesh(
      clickTargetGeometry,
      clickTargetMaterial
    );
    clickTarget.rotation.x = -Math.PI / 2;
    clickTarget.position.y = 0.1; // Above cell meshes at 0.01
    clickTarget.name = "clickTarget";
    group.add(clickTarget);

    // Position on grid
    group.position.set(token.x + 0.5, 0, token.y + 0.5);

    return {
      group,
      mesh,
      ring,
      tokenId: token.id,
      targetX: token.x + 0.5,
      targetZ: token.y + 0.5,
      animating: false,
      animStartX: token.x + 0.5,
      animStartZ: token.y + 0.5,
      animProgress: 0,
      animDistance: 0,
      trailParticles: [],
    };
  }

  // Trail particle geometry (reused)
  const trailGeometry = new THREE.SphereGeometry(0.08, 8, 8);

  function createTrailParticle(
    x: number,
    y: number,
    z: number,
    intensity: number
  ): THREE.Mesh {
    // Color from yellow to orange based on intensity
    const color = new THREE.Color().setHSL(
      0.1 - intensity * 0.1,
      1,
      0.5 + intensity * 0.3
    );
    const material = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.8 * intensity,
    });
    const particle = new THREE.Mesh(trailGeometry, material);
    particle.position.set(x, y, z);
    particle.scale.setScalar(0.5 + intensity * 1.5); // Bigger for longer jumps
    return particle;
  }

  function getSquashStretch(
    progress: number,
    distance: number
  ): {
    scaleX: number;
    scaleY: number;
  } {
    // Sequence: squish -> tall -> arc (stretched) -> land -> squish -> normal
    const intensity = Math.min(distance / 3, 2);
    const t = progress;

    let squash: number;
    if (t < 0.1) {
      // 1. Squish down (preparing to jump)
      const p = t / 0.1;
      squash = 1.2 * p; // Ease into squash
    } else if (t < 0.2) {
      // 2. Get tall (stretch up to launch)
      const p = (t - 0.1) / 0.1;
      squash = 1.2 - 2.7 * p; // From squash (1.2) to stretch (-1.5)
    } else if (t < 0.8) {
      // 3. Jump the arc (stay stretched tall)
      squash = -1.5;
    } else if (t < 0.9) {
      // 4. About to land (still stretched)
      squash = -1.5;
    } else if (t < 0.97) {
      // 5. Squish flat (impact!)
      const p = (t - 0.9) / 0.07;
      squash = -1.5 + 3.0 * p; // From stretch (-1.5) to squash (1.5)
    } else {
      // 6. Return to normal
      const p = (t - 0.97) / 0.03;
      squash = 1.5 * (1 - p); // Squash back to normal
    }

    // Scale effect by jump distance
    squash *= intensity;

    // squash > 0 = wider and shorter, squash < 0 = taller and narrower
    return {
      scaleX: 1 + squash * 0.9,
      scaleY: 1 - squash * 0.85,
    };
  }

  // Animation constants
  const ANIM_DURATION = 500; // ms
  let animationFrameId: number | null = null;
  let lastAnimTime = 0;

  function getArcPosition(
    startX: number,
    startZ: number,
    endX: number,
    endZ: number,
    progress: number
  ): { x: number; y: number; z: number } {
    const t = progress;
    const x = startX + (endX - startX) * t;
    const z = startZ + (endZ - startZ) * t;

    // Match the pending arc formula: semi-circle with radius = distance/2
    const distance = Math.sqrt((endX - startX) ** 2 + (endZ - startZ) ** 2);
    const radius = distance / 2;
    const y = Math.sin(Math.PI * t) * radius;

    return { x, y, z };
  }

  function updateAnimations(deltaTime: number) {
    let anyAnimating = false;

    for (const piece of pieces.value.values()) {
      // Update trail particles (fade and shrink)
      for (let i = piece.trailParticles.length - 1; i >= 0; i--) {
        const particle = piece.trailParticles[i];
        const mat = particle.material as THREE.MeshBasicMaterial;
        mat.opacity -= deltaTime * 0.003;
        particle.scale.multiplyScalar(0.96);

        if (mat.opacity <= 0) {
          if (piecesGroup.value) piecesGroup.value.remove(particle);
          mat.dispose();
          piece.trailParticles.splice(i, 1);
        }
      }

      if (!piece.animating) continue;

      anyAnimating = true;
      piece.animProgress += deltaTime / ANIM_DURATION;

      if (piece.animProgress >= 1) {
        // Animation complete
        piece.animProgress = 1;
        piece.animating = false;
        piece.group.position.set(piece.targetX, 0, piece.targetZ);
        piece.animStartX = piece.targetX;
        piece.animStartZ = piece.targetZ;

        // Reset mesh scale
        piece.mesh.scale.set(1, 1, 1);
      } else {
        // Interpolate along arc
        const pos = getArcPosition(
          piece.animStartX,
          piece.animStartZ,
          piece.targetX,
          piece.targetZ,
          piece.animProgress
        );
        piece.group.position.set(pos.x, pos.y, pos.z);

        // Apply squash-stretch (more exaggerated for longer jumps)
        const { scaleX, scaleY } = getSquashStretch(
          piece.animProgress,
          piece.animDistance
        );
        piece.mesh.scale.set(scaleX, scaleY, 1);

        // Spawn trail particles (more for longer jumps)
        const intensity = Math.min(piece.animDistance / 10, 1); // Normalize by max expected distance
        if (intensity > 0.1 && Math.random() < intensity * 0.5) {
          const particle = createTrailParticle(
            pos.x,
            pos.y + 0.2,
            pos.z,
            intensity
          );
          if (piecesGroup.value) {
            piecesGroup.value.add(particle);
            piece.trailParticles.push(particle);
          }
        }
      }
    }

    // Keep animating if there are trail particles
    for (const piece of pieces.value.values()) {
      if (piece.trailParticles.length > 0) anyAnimating = true;
    }

    return anyAnimating;
  }

  function animationLoop(currentTime: number) {
    const deltaTime = lastAnimTime ? currentTime - lastAnimTime : 16;
    lastAnimTime = currentTime;

    const stillAnimating = updateAnimations(deltaTime);

    if (stillAnimating) {
      animationFrameId = requestAnimationFrame(animationLoop);
    } else {
      animationFrameId = null;
      lastAnimTime = 0;
    }
  }

  function startAnimationLoop() {
    if (animationFrameId === null) {
      lastAnimTime = 0;
      animationFrameId = requestAnimationFrame(animationLoop);
    }
  }

  // Update ring style when selection changes (filled square for selected, outline for not)
  function updateSelectionRing() {
    if (!selectedPieceId) return;

    for (const [id, piece] of pieces.value.entries()) {
      const isSelected = String(id) === String(selectedPieceId.value);
      const token = gameState.value?.tokens?.[String(id)];
      const isPlayerPiece =
        token && playerAddress.value && token.owner === playerAddress.value;

      // Only update ring for player pieces
      if (isPlayerPiece) {
        // Remove old ring
        const oldRing = piece.group.getObjectByName("ownerRing");
        if (oldRing) {
          piece.group.remove(oldRing);
          if (oldRing instanceof THREE.Mesh) {
            oldRing.geometry?.dispose();
            (oldRing.material as THREE.Material)?.dispose();
          }
        }

        // Filled square - blue for selected, green for unselected
        const material = new THREE.MeshBasicMaterial({
          color: isSelected
            ? OWNERSHIP_COLORS.selected
            : OWNERSHIP_COLORS.player,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.6,
        });
        const newRing = new THREE.Mesh(filledSquareGeometry, material);
        newRing.rotation.x = -Math.PI / 2;
        newRing.position.y = 0.02;
        newRing.name = "ownerRing";
        newRing.raycast = () => {}; // Disable raycasting - use clickTarget instead
        piece.group.add(newRing);
        piece.ring = newRing;
      }
    }
  }

  function syncPieces() {
    if (!scene.value || !piecesGroup.value) {
      console.warn("[usePieceRenderer] No scene or group, skipping sync");
      return;
    }

    const tokens = gameState.value?.tokens || {};
    const currentIds = new Set(Object.keys(tokens));
    const existingIds = new Set(pieces.value.keys());

    // Remove pieces that no longer exist
    for (const id of existingIds) {
      if (!currentIds.has(String(id))) {
        const piece = pieces.value.get(id);
        if (piece) {
          piecesGroup.value.remove(piece.group);
          // Dispose geometry/materials
          piece.group.traverse((obj) => {
            if (obj instanceof THREE.Mesh) {
              obj.geometry?.dispose();
              if (Array.isArray(obj.material)) {
                obj.material.forEach((m) => m.dispose());
              } else {
                obj.material?.dispose();
              }
            }
          });
          pieces.value.delete(id);
        }
      }
    }

    // Add or update pieces
    let needsAnimation = false;
    for (const [id, token] of Object.entries(tokens)) {
      const existing = pieces.value.get(id);
      if (existing) {
        const newX = token.x + 0.5;
        const newZ = token.y + 0.5;

        // Check if position changed
        if (
          Math.abs(existing.targetX - newX) > 0.01 ||
          Math.abs(existing.targetZ - newZ) > 0.01
        ) {
          // Start animation from current position to new position
          existing.animStartX = existing.group.position.x;
          existing.animStartZ = existing.group.position.z;
          existing.targetX = newX;
          existing.targetZ = newZ;
          existing.animProgress = 0;
          existing.animating = true;
          // Calculate distance for trail intensity
          existing.animDistance = Math.sqrt(
            (newX - existing.animStartX) ** 2 +
              (newZ - existing.animStartZ) ** 2
          );
          needsAnimation = true;
        }
      } else {
        // Create new piece
        const piece = createPieceSprite(token);
        piecesGroup.value.add(piece.group);
        pieces.value.set(id, piece);
      }
    }

    // Start animation loop if any pieces moved
    if (needsAnimation) {
      startAnimationLoop();
    }

    // Force reactivity update
    pieces.value = new Map(pieces.value);

    // Update selection rings after sync
    updateSelectionRing();
  }

  function initGroup() {
    if (!scene.value) return;

    // Remove existing group
    if (piecesGroup.value) {
      scene.value.remove(piecesGroup.value);
    }

    const group = new THREE.Group();
    group.name = "piecesGroup";
    scene.value.add(group);
    piecesGroup.value = group;
    syncPieces();
    syncPieces();
  }

  // Watch for scene changes
  watch(
    scene,
    (newScene) => {
      if (newScene) initGroup();
    },
    { immediate: true }
  );

  watch(gameState, () => syncPieces(), { deep: true });

  watch(playerAddress, () => {
    if (piecesGroup.value) {
      for (const piece of pieces.value.values()) {
        piecesGroup.value.remove(piece.group);
      }
      pieces.value.clear();
      syncPieces();
    }
  });

  // Watch for selection changes
  if (selectedPieceId) {
    watch(selectedPieceId, () => updateSelectionRing(), { immediate: true });
  }

  function getPieceAt(x: number, z: number): PieceSprite | undefined {
    for (const piece of pieces.value.values()) {
      const px = Math.floor(piece.group.position.x);
      const pz = Math.floor(piece.group.position.z);
      if (px === x && pz === z) {
        return piece;
      }
    }
    return undefined;
  }

  // Cleanup animation loop on unmount
  onUnmounted(() => {
    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }
  });

  return {
    pieces,
    piecesGroup,
    getPieceAt,
    syncPieces,
  };
}
