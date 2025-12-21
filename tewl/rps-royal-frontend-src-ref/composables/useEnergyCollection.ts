/**
 * useEnergyCollection - Particle effects when collecting energy pieces
 *
 * Creates golden particle burst that spirals toward collector piece.
 */

import { type Ref, shallowRef, onUnmounted } from "vue";
import * as THREE from "three";

const PARTICLE_COUNT = 24;
const PARTICLE_COLOR = 0xffd700; // Gold
const ANIMATION_DURATION = 500; // ms
const SPIRAL_TURNS = 1.5;

interface Particle {
  mesh: THREE.Mesh;
  startPos: THREE.Vector3;
  angle: number; // Initial angle for spiral
  delay: number; // Stagger start
}

interface CollectionEffect {
  particles: Particle[];
  targetPos: THREE.Vector3;
  startTime: number;
  onComplete?: () => void;
}

export function useEnergyCollection(scene: Ref<THREE.Scene | null>) {
  const activeEffects = shallowRef<CollectionEffect[]>([]);
  let animationFrameId: number | null = null;

  // Shared geometry for particles
  const particleGeometry = new THREE.SphereGeometry(0.06, 8, 8);
  const particleMaterial = new THREE.MeshBasicMaterial({
    color: PARTICLE_COLOR,
    transparent: true,
  });

  function createParticles(
    sourcePos: THREE.Vector3,
    count: number
  ): Particle[] {
    const particles: Particle[] = [];

    for (let i = 0; i < count; i++) {
      const mesh = new THREE.Mesh(
        particleGeometry,
        particleMaterial.clone() // Clone material for individual opacity
      );

      // Random offset around source position (burst effect)
      const angle = (i / count) * Math.PI * 2;
      const radius = 0.3 + Math.random() * 0.2;
      const offsetX = Math.cos(angle) * radius;
      const offsetZ = Math.sin(angle) * radius;
      const offsetY = 0.2 + Math.random() * 0.3;

      const startPos = new THREE.Vector3(
        sourcePos.x + offsetX,
        sourcePos.y + offsetY,
        sourcePos.z + offsetZ
      );
      mesh.position.copy(startPos);
      mesh.scale.setScalar(0.8 + Math.random() * 0.4);

      particles.push({
        mesh,
        startPos,
        angle,
        delay: (i / count) * 100, // Stagger up to 100ms
      });
    }

    return particles;
  }

  function playCollectionEffect(
    sourceX: number,
    sourceY: number,
    targetX: number,
    targetY: number,
    onComplete?: () => void
  ) {
    if (!scene.value) return;

    // Convert grid coords to 3D (center of cell)
    const sourcePos = new THREE.Vector3(sourceX + 0.5, 0.1, sourceY + 0.5);
    const targetPos = new THREE.Vector3(targetX + 0.5, 0.5, targetY + 0.5);

    const particles = createParticles(sourcePos, PARTICLE_COUNT);

    // Add particles to scene
    for (const p of particles) {
      scene.value.add(p.mesh);
    }

    const effect: CollectionEffect = {
      particles,
      targetPos,
      startTime: performance.now(),
      onComplete,
    };

    activeEffects.value = [...activeEffects.value, effect];
    startAnimationLoop();
  }

  function updateEffects(currentTime: number) {
    const newEffects: CollectionEffect[] = [];

    for (const effect of activeEffects.value) {
      let allComplete = true;

      for (const particle of effect.particles) {
        const elapsed = currentTime - effect.startTime - particle.delay;

        if (elapsed < 0) {
          // Not started yet
          allComplete = false;
          continue;
        }

        const progress = Math.min(elapsed / ANIMATION_DURATION, 1);

        if (progress < 1) {
          allComplete = false;

          // Ease-in for acceleration toward target
          const easedProgress = progress * progress;

          // Spiral path: start wide, converge to target
          const spiralAngle =
            particle.angle + easedProgress * Math.PI * 2 * SPIRAL_TURNS;
          const spiralRadius = (1 - easedProgress) * 0.5;

          // Lerp from start to target with spiral offset
          const baseX =
            particle.startPos.x +
            (effect.targetPos.x - particle.startPos.x) * easedProgress;
          const baseY =
            particle.startPos.y +
            (effect.targetPos.y - particle.startPos.y) * easedProgress;
          const baseZ =
            particle.startPos.z +
            (effect.targetPos.z - particle.startPos.z) * easedProgress;

          particle.mesh.position.set(
            baseX + Math.cos(spiralAngle) * spiralRadius,
            baseY + Math.sin(progress * Math.PI) * 0.3, // Arc up then down
            baseZ + Math.sin(spiralAngle) * spiralRadius
          );

          // Fade and shrink as approaching target
          const mat = particle.mesh.material as THREE.MeshBasicMaterial;
          mat.opacity = 1 - easedProgress * 0.5;
          particle.mesh.scale.setScalar((1 - easedProgress * 0.7) * 1.2);
        }
      }

      if (allComplete) {
        // Cleanup particles
        for (const particle of effect.particles) {
          if (scene.value) {
            scene.value.remove(particle.mesh);
          }
          (particle.mesh.material as THREE.Material).dispose();
        }
        effect.onComplete?.();
      } else {
        newEffects.push(effect);
      }
    }

    activeEffects.value = newEffects;
    return newEffects.length > 0;
  }

  function animationLoop() {
    const stillActive = updateEffects(performance.now());

    if (stillActive) {
      animationFrameId = requestAnimationFrame(animationLoop);
    } else {
      animationFrameId = null;
    }
  }

  function startAnimationLoop() {
    if (animationFrameId === null) {
      animationFrameId = requestAnimationFrame(animationLoop);
    }
  }

  // Cleanup on unmount
  onUnmounted(() => {
    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId);
    }

    // Remove any remaining particles
    for (const effect of activeEffects.value) {
      for (const particle of effect.particles) {
        if (scene.value) {
          scene.value.remove(particle.mesh);
        }
        (particle.mesh.material as THREE.Material).dispose();
      }
    }

    particleGeometry.dispose();
    particleMaterial.dispose();
  });

  return {
    playCollectionEffect,
  };
}

