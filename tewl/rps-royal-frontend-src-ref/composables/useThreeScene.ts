/**
 * useThreeScene - Three.js scene lifecycle management for Vue
 */

import { ref, shallowRef, onMounted, onUnmounted, watch, type Ref } from "vue";
import * as THREE from "three";

// Scene configuration
const CAMERA_FOV = 30;
const CAMERA_NEAR = 0.1;
const CAMERA_FAR = 1000;
const CAMERA_HEIGHT = 50;
const CAMERA_DISTANCE = 50;
const AMBIENT_INTENSITY = 0.6;
const DIRECTIONAL_INTENSITY = 0.8;

export function useThreeScene(container: Ref<HTMLElement | null>) {
  console.log("[useThreeScene] Composable created");

  const scene = shallowRef<THREE.Scene | null>(null);
  const camera = shallowRef<THREE.PerspectiveCamera | null>(null);
  const renderer = shallowRef<THREE.WebGLRenderer | null>(null);
  const isInitialized = ref(false);

  let animationFrameId: number | null = null;
  let frameCount = 0;

  function init() {
    console.log("[useThreeScene] init() called, container:", container.value);

    if (!container.value) {
      console.warn("[useThreeScene] No container, skipping init");
      return;
    }

    if (isInitialized.value) {
      console.warn("[useThreeScene] Already initialized, skipping");
      return;
    }

    console.log("[useThreeScene] Creating scene...");

    // Scene with black background
    const newScene = new THREE.Scene();
    newScene.background = new THREE.Color(0x000000);
    scene.value = newScene;

    console.log("[useThreeScene] Scene created:", newScene);

    // Camera
    const width = container.value.clientWidth;
    const height = container.value.clientHeight;
    console.log("[useThreeScene] Container size:", width, "x", height);

    const aspect = width / height;
    const newCamera = new THREE.PerspectiveCamera(
      CAMERA_FOV,
      aspect,
      CAMERA_NEAR,
      CAMERA_FAR
    );
    newCamera.position.set(0, CAMERA_HEIGHT, CAMERA_DISTANCE);
    newCamera.lookAt(0, 0, 0);
    camera.value = newCamera;
    console.log("[useThreeScene] Camera created at:", newCamera.position);

    // Renderer
    const newRenderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
    });
    newRenderer.setSize(width, height);
    newRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    newRenderer.shadowMap.enabled = true;
    newRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
    newRenderer.domElement.style.display = "block"; // Ensure canvas is visible
    container.value.appendChild(newRenderer.domElement);
    renderer.value = newRenderer;
    console.log("[useThreeScene] Renderer created, canvas appended");

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, AMBIENT_INTENSITY);
    newScene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(
      0xffffff,
      DIRECTIONAL_INTENSITY
    );
    directionalLight.position.set(10, 20, 10);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 1024;
    directionalLight.shadow.mapSize.height = 1024;
    directionalLight.shadow.camera.near = 0.5;
    directionalLight.shadow.camera.far = 100;
    directionalLight.shadow.camera.left = -30;
    directionalLight.shadow.camera.right = 30;
    directionalLight.shadow.camera.top = 30;
    directionalLight.shadow.camera.bottom = -30;
    newScene.add(directionalLight);

    console.log("[useThreeScene] Scene children:", newScene.children.length);

    isInitialized.value = true;
    console.log(
      "[useThreeScene] ✅ Initialization complete, starting animation loop"
    );

    // Start animation loop
    animate();
  }

  function animate() {
    if (!renderer.value || !scene.value || !camera.value) {
      console.warn("[useThreeScene] animate() - missing refs, stopping");
      return;
    }

    animationFrameId = requestAnimationFrame(animate);
    frameCount++;

    // Log every 300 frames (~5 seconds at 60fps)
    if (frameCount % 300 === 0) {
      console.log(
        "[useThreeScene] Frame:",
        frameCount,
        "Scene children:",
        scene.value.children.length
      );
    }

    renderer.value.render(scene.value, camera.value);
  }

  function handleResize() {
    if (!container.value || !camera.value || !renderer.value) return;

    const width = container.value.clientWidth;
    const height = container.value.clientHeight;
    console.log("[useThreeScene] Resize:", width, "x", height);

    camera.value.aspect = width / height;
    camera.value.updateProjectionMatrix();
    renderer.value.setSize(width, height);
  }

  function dispose() {
    console.log("[useThreeScene] ⚠️ dispose() called");

    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }

    if (renderer.value) {
      renderer.value.dispose();
      renderer.value.domElement.remove();
      renderer.value = null;
    }

    if (scene.value) {
      scene.value.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry?.dispose();
          if (Array.isArray(object.material)) {
            object.material.forEach((m) => m.dispose());
          } else {
            object.material?.dispose();
          }
        }
      });
      scene.value = null;
    }

    camera.value = null;
    isInitialized.value = false;
    console.log("[useThreeScene] Disposed");
  }

  // Watch container for changes
  watch(container, (newContainer, oldContainer) => {
    console.log("[useThreeScene] Container changed:", {
      old: !!oldContainer,
      new: !!newContainer,
    });
    if (newContainer && !isInitialized.value) {
      init();
    }
  });

  onMounted(() => {
    console.log("[useThreeScene] onMounted, container:", !!container.value);
    if (container.value) {
      init();
    }
    window.addEventListener("resize", handleResize);
  });

  onUnmounted(() => {
    console.log("[useThreeScene] onUnmounted");
    window.removeEventListener("resize", handleResize);
    dispose();
  });

  return {
    scene,
    camera,
    renderer,
    isInitialized,
  };
}
