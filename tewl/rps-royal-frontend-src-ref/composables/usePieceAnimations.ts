/**
 * usePieceAnimations - GSAP-powered piece animations
 *
 * Animations:
 * - Idle: Subtle Y-axis bob
 * - Selection: Pop up + scale
 * - Movement: Arc hop to new cell
 * - Combat win: Bounce
 * - Combat lose: Crumple and fade
 * - Spawn: Scale up from zero
 */

import gsap from "gsap";
import * as THREE from "three";

// Animation durations
const HOP_DURATION = 0.3;
const HOP_HEIGHT = 0.8;
const SELECT_DURATION = 0.2;
const COMBAT_DURATION = 0.4;
const SPAWN_DURATION = 0.3;
const IDLE_BOB_DURATION = 2;
const IDLE_BOB_AMOUNT = 0.05;

export function usePieceAnimations() {
  // Track active idle animations
  const idleAnimations = new Map<string, gsap.core.Tween>();

  /**
   * Start idle bob animation on a piece
   */
  function startIdleBob(pieceId: string, group: THREE.Group) {
    // Stop existing animation if any
    stopIdleBob(pieceId);

    const baseY = group.position.y;
    const tween = gsap.to(group.position, {
      y: baseY + IDLE_BOB_AMOUNT,
      duration: IDLE_BOB_DURATION / 2,
      ease: "sine.inOut",
      yoyo: true,
      repeat: -1,
    });

    idleAnimations.set(pieceId, tween);
  }

  /**
   * Stop idle bob animation
   */
  function stopIdleBob(pieceId: string) {
    const existing = idleAnimations.get(pieceId);
    if (existing) {
      existing.kill();
      idleAnimations.delete(pieceId);
    }
  }

  /**
   * Selection pop animation
   */
  function selectPop(group: THREE.Group) {
    // Scale up briefly then back
    gsap.timeline()
      .to(group.scale, {
        x: 1.2,
        y: 1.2,
        z: 1.2,
        duration: SELECT_DURATION / 2,
        ease: "back.out(2)",
      })
      .to(group.scale, {
        x: 1.1,
        y: 1.1,
        z: 1.1,
        duration: SELECT_DURATION / 2,
        ease: "power2.out",
      });

    // Slight hop
    gsap.to(group.position, {
      y: group.position.y + 0.2,
      duration: SELECT_DURATION / 2,
      ease: "power2.out",
      yoyo: true,
      repeat: 1,
    });
  }

  /**
   * Deselection - return to normal scale
   */
  function deselect(group: THREE.Group) {
    gsap.to(group.scale, {
      x: 1,
      y: 1,
      z: 1,
      duration: SELECT_DURATION,
      ease: "power2.out",
    });
  }

  /**
   * Hop movement animation
   */
  function hopTo(
    group: THREE.Group,
    targetX: number,
    targetZ: number,
    onComplete?: () => void
  ) {
    const startY = group.position.y;

    // Create timeline for coordinated movement
    const tl = gsap.timeline({
      onComplete: () => {
        group.position.y = startY; // Reset to base height
        onComplete?.();
      },
    });

    // Horizontal movement
    tl.to(
      group.position,
      {
        x: targetX,
        z: targetZ,
        duration: HOP_DURATION,
        ease: "power2.inOut",
      },
      0
    );

    // Vertical arc (hop up then down)
    tl.to(
      group.position,
      {
        y: startY + HOP_HEIGHT,
        duration: HOP_DURATION / 2,
        ease: "power2.out",
      },
      0
    ).to(
      group.position,
      {
        y: startY,
        duration: HOP_DURATION / 2,
        ease: "power2.in",
      },
      HOP_DURATION / 2
    );

    return tl;
  }

  /**
   * Combat win - bounce celebration
   */
  function combatWin(group: THREE.Group) {
    gsap.timeline()
      .to(group.scale, {
        x: 1.3,
        y: 1.3,
        z: 1.3,
        duration: COMBAT_DURATION / 3,
        ease: "back.out(3)",
      })
      .to(group.scale, {
        x: 1,
        y: 1,
        z: 1,
        duration: COMBAT_DURATION / 3,
        ease: "elastic.out(1, 0.5)",
      });

    // Victory hop
    gsap.to(group.position, {
      y: group.position.y + 0.5,
      duration: COMBAT_DURATION / 2,
      ease: "power2.out",
      yoyo: true,
      repeat: 1,
    });
  }

  /**
   * Combat lose - crumple and fade (paper effect)
   */
  function combatLose(group: THREE.Group, onComplete?: () => void) {
    gsap.timeline({ onComplete })
      // Flatten vertically (crumple)
      .to(group.scale, {
        y: 0.1,
        duration: COMBAT_DURATION / 2,
        ease: "power2.in",
      })
      // Fade out
      .to(
        group,
        {
          duration: COMBAT_DURATION / 2,
          ease: "power2.out",
          onUpdate: function () {
            // Fade all materials in the group
            group.traverse((child) => {
              if (child instanceof THREE.Mesh || child instanceof THREE.Sprite) {
                const material = child.material as THREE.Material;
                if (material && "opacity" in material) {
                  material.opacity = 1 - this.progress();
                  material.transparent = true;
                }
              }
            });
          },
        },
        "-=0.1"
      );
  }

  /**
   * Spawn animation - scale up from zero
   */
  function spawn(group: THREE.Group) {
    // Start at zero scale
    group.scale.set(0, 0, 0);

    gsap.to(group.scale, {
      x: 1,
      y: 1,
      z: 1,
      duration: SPAWN_DURATION,
      ease: "back.out(2)",
    });

    // Pop up from ground
    const targetY = group.position.y;
    group.position.y = 0;
    gsap.to(group.position, {
      y: targetY,
      duration: SPAWN_DURATION,
      ease: "power2.out",
    });
  }

  /**
   * Cleanup all animations
   */
  function cleanup() {
    idleAnimations.forEach((tween) => tween.kill());
    idleAnimations.clear();
  }

  return {
    startIdleBob,
    stopIdleBob,
    selectPop,
    deselect,
    hopTo,
    combatWin,
    combatLose,
    spawn,
    cleanup,
  };
}

