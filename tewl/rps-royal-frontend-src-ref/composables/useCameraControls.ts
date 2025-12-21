/**
 * useCameraControls - RTS style camera
 *
 * Features:
 * - Fixed isometric angle (no rotation)
 * - Left-click drag to pan (with threshold to allow clicks)
 * - Edge scrolling when cursor near screen edge
 * - WASD/arrow keys to pan
 * - Scroll wheel zoom
 * - Panning limited to grid bounds
 */

import { ref, shallowRef, watch, onUnmounted, type Ref } from "vue";
import * as THREE from "three";

// Camera settings
const MIN_ZOOM = 15;
const MAX_ZOOM = 100;
const KEYBOARD_PAN_SPEED = 0.3;
const ZOOM_SPEED = 2;
const EDGE_SCROLL_ZONE = 50; // pixels from edge (larger margin)
const EDGE_SCROLL_SPEED = 0.3;
const PAN_DURATION = 400; // ms for smooth pan

// UI margins to exclude from edge scroll detection
const HEADER_HEIGHT = 70; // header bar height
const BOTTOM_BAR_COLLAPSED = 60; // collapsed bottom bar
const BOTTOM_BAR_EXPANDED = 350; // expanded bottom bar (approximate)

// Grid bounds (will be updated dynamically)
const DEFAULT_BOUNDS = { min: -25, max: 25 };

export function useCameraControls(
  camera: Ref<THREE.PerspectiveCamera | null>,
  renderer: Ref<THREE.WebGLRenderer | null>,
  scene: Ref<THREE.Scene | null>,
  gridBounds?: Ref<{ min: number; max: number }>,
  hoveredCell?: Ref<{ x: number; y: number } | null>
) {
  console.log("[useCameraControls] Composable created (AoE style)");

  // Camera target (what the camera looks at)
  const target = shallowRef(new THREE.Vector3(0, 0, 0));
  const currentZoom = ref(15); // Distance from target

  // Input state
  const isDragging = ref(false);
  const dragStartWorldPos = new THREE.Vector3();
  const dragStartScreenPos = { x: 0, y: 0 };
  const currentMousePos = { x: 0, y: 0 };
  const keysPressed = new Set<string>();
  const isMouseInCanvas = ref(false);
  const DRAG_THRESHOLD = 5; // pixels before considering it a drag

  // Raycaster for screen-to-world
  const raycaster = new THREE.Raycaster();
  const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0); // Y=0 plane

  // Animation state
  let panAnimation: number | null = null;
  let animationFrameId: number | null = null;
  let canvasRect: DOMRect | null = null;

  function getBounds() {
    return gridBounds?.value || DEFAULT_BOUNDS;
  }

  function clampTarget() {
    const bounds = getBounds();
    // Grid spans from min to max+1 (cells are 1 unit wide), center at (min+max+1)/2
    target.value.x = Math.max(
      bounds.min,
      Math.min(bounds.max + 1, target.value.x)
    );
    target.value.z = Math.max(
      bounds.min,
      Math.min(bounds.max + 1, target.value.z)
    );
  }

  function updateCameraPosition() {
    if (!camera.value) return;

    // Fixed isometric angle: looking down at ~45°
    const angle = Math.PI / 4; // 45 degrees
    const height = currentZoom.value * Math.sin(angle);
    const distance = currentZoom.value * Math.cos(angle);

    camera.value.position.set(
      target.value.x,
      height,
      target.value.z + distance
    );
    camera.value.lookAt(target.value);
  }

  function panBy(dx: number, dz: number) {
    target.value.x += dx;
    target.value.z += dz;
    clampTarget();
    updateCameraPosition();
  }

  function zoomBy(delta: number) {
    currentZoom.value = Math.max(
      MIN_ZOOM,
      Math.min(MAX_ZOOM, currentZoom.value + delta)
    );
    updateCameraPosition();
  }

  /**
   * Get world position on the ground plane from screen coordinates
   */
  function screenToWorld(
    screenX: number,
    screenY: number
  ): THREE.Vector3 | null {
    if (!camera.value || !canvasRect) return null;

    // Convert to normalized device coordinates
    const ndcX = ((screenX - canvasRect.left) / canvasRect.width) * 2 - 1;
    const ndcY = -((screenY - canvasRect.top) / canvasRect.height) * 2 + 1;

    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera.value);

    const intersection = new THREE.Vector3();
    const hit = raycaster.ray.intersectPlane(groundPlane, intersection);

    return hit ? intersection : null;
  }

  /**
   * Smoothly pan camera to focus on a world position
   */
  function panTo(x: number, z: number, duration = PAN_DURATION) {
    if (!camera.value) return;

    // Cancel any ongoing pan
    if (panAnimation) {
      cancelAnimationFrame(panAnimation);
    }

    const startTarget = target.value.clone();
    const endTarget = new THREE.Vector3(
      Math.max(getBounds().min, Math.min(getBounds().max + 1, x)),
      0,
      Math.max(getBounds().min, Math.min(getBounds().max + 1, z))
    );
    const startTime = performance.now();

    console.log("[useCameraControls] Pan to", x, z);

    function animate() {
      const elapsed = performance.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);

      target.value.lerpVectors(startTarget, endTarget, eased);
      updateCameraPosition();

      if (progress < 1) {
        panAnimation = requestAnimationFrame(animate);
      } else {
        panAnimation = null;
        console.log("[useCameraControls] Pan complete");
      }
    }

    panAnimation = requestAnimationFrame(animate);
  }

  /**
   * Pan to a piece's position
   */
  function panToPiece(pieceX: number, pieceY: number) {
    panTo(pieceX + 0.5, pieceY + 0.5);
  }

  /**
   * Reset camera to default view
   */
  function resetCamera() {
    currentZoom.value = 50;
    panTo(0, 0);
  }

  // Input handlers
  function onMouseDown(e: MouseEvent) {
    // Left-click for drag panning
    if (e.button === 0) {
      dragStartScreenPos.x = e.clientX;
      dragStartScreenPos.y = e.clientY;
      const worldPos = screenToWorld(e.clientX, e.clientY);
      if (worldPos) {
        dragStartWorldPos.copy(worldPos);
      }
    }
  }

  function onMouseUp(e: MouseEvent) {
    if (e.button === 0) {
      isDragging.value = false;
    }
  }

  function onContextMenu(e: MouseEvent) {
    e.preventDefault();
  }

  function onMouseMove(e: MouseEvent) {
    currentMousePos.x = e.clientX;
    currentMousePos.y = e.clientY;

    // Check if we should start dragging (left button held + moved past threshold)
    if (e.buttons === 1 && !isDragging.value) {
      const dx = e.clientX - dragStartScreenPos.x;
      const dy = e.clientY - dragStartScreenPos.y;
      if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
        isDragging.value = true;
        // Re-capture world position at drag start
        const worldPos = screenToWorld(e.clientX, e.clientY);
        if (worldPos) dragStartWorldPos.copy(worldPos);
      }
    }

    // Handle drag panning
    if (isDragging.value) {
      const currentWorldPos = screenToWorld(e.clientX, e.clientY);
      if (currentWorldPos) {
        const dx = dragStartWorldPos.x - currentWorldPos.x;
        const dz = dragStartWorldPos.z - currentWorldPos.z;

        target.value.x += dx;
        target.value.z += dz;
        clampTarget();
        updateCameraPosition();

        const newWorldPos = screenToWorld(e.clientX, e.clientY);
        if (newWorldPos) dragStartWorldPos.copy(newWorldPos);
      }
    }
  }

  function onMouseEnter() {
    isMouseInCanvas.value = true;
  }

  function onMouseLeave() {
    isMouseInCanvas.value = false;
    isDragging.value = false;
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    zoomBy(e.deltaY * 0.05 * ZOOM_SPEED);
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

  function onKeyDown(e: KeyboardEvent) {
    if (isInputFocused()) return;
    keysPressed.add(e.key.toLowerCase());
  }

  function onKeyUp(e: KeyboardEvent) {
    if (isInputFocused()) return;
    keysPressed.delete(e.key.toLowerCase());
  }

  // Combined input loop (keyboard + edge scroll)
  function updateInputLoop() {
    let dx = 0;
    let dz = 0;

    // Keyboard panning
    if (keysPressed.has("w") || keysPressed.has("arrowup"))
      dz -= KEYBOARD_PAN_SPEED;
    if (keysPressed.has("s") || keysPressed.has("arrowdown"))
      dz += KEYBOARD_PAN_SPEED;
    if (keysPressed.has("a") || keysPressed.has("arrowleft"))
      dx -= KEYBOARD_PAN_SPEED;
    if (keysPressed.has("d") || keysPressed.has("arrowright"))
      dx += KEYBOARD_PAN_SPEED;

    // Edge scrolling (only when mouse is in canvas, not dragging, and over grid)
    // If hoveredCell is provided, only edge-scroll when mouse is over a grid cell
    const isOverGrid = !hoveredCell || hoveredCell.value !== null;
    if (
      isMouseInCanvas.value &&
      !isDragging.value &&
      canvasRect &&
      isOverGrid
    ) {
      const mouseX = currentMousePos.x;
      const mouseY = currentMousePos.y;

      // Canvas boundaries
      const canvasLeft = canvasRect.left;
      const canvasRight = canvasRect.right;
      const canvasTop = canvasRect.top;
      const canvasBottom = canvasRect.bottom;

      // Left edge of screen
      if (mouseX < canvasLeft + EDGE_SCROLL_ZONE) {
        const distFromEdge = mouseX - canvasLeft;
        if (distFromEdge > 0) {
          dx -= EDGE_SCROLL_SPEED * (1 - distFromEdge / EDGE_SCROLL_ZONE);
        }
      }
      // Right edge of screen
      if (mouseX > canvasRight - EDGE_SCROLL_ZONE) {
        const distFromEdge = canvasRight - mouseX;
        if (distFromEdge > 0) {
          dx += EDGE_SCROLL_SPEED * (1 - distFromEdge / EDGE_SCROLL_ZONE);
        }
      }
      // Top edge (below header)
      if (mouseY < canvasTop + EDGE_SCROLL_ZONE) {
        const distFromEdge = mouseY - canvasTop;
        if (distFromEdge > 0) {
          dz -= EDGE_SCROLL_SPEED * (1 - distFromEdge / EDGE_SCROLL_ZONE);
        }
      }
      // Bottom edge (above bottom bar)
      if (mouseY > canvasBottom - EDGE_SCROLL_ZONE) {
        const distFromEdge = canvasBottom - mouseY;
        if (distFromEdge > 0) {
          dz += EDGE_SCROLL_SPEED * (1 - distFromEdge / EDGE_SCROLL_ZONE);
        }
      }
    }

    if (dx !== 0 || dz !== 0) {
      panBy(dx, dz);
    }

    animationFrameId = requestAnimationFrame(updateInputLoop);
  }

  function init() {
    if (!renderer.value) return;

    const domElement = renderer.value.domElement;
    canvasRect = domElement.getBoundingClientRect();

    domElement.addEventListener("mousedown", onMouseDown);
    domElement.addEventListener("mouseup", onMouseUp);
    domElement.addEventListener("mousemove", onMouseMove);
    domElement.addEventListener("mouseenter", onMouseEnter);
    domElement.addEventListener("mouseleave", onMouseLeave);
    domElement.addEventListener("contextmenu", onContextMenu);
    domElement.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("resize", onResize);

    // Initial camera position
    updateCameraPosition();

    // Start input loop (keyboard + edge scroll)
    animationFrameId = requestAnimationFrame(updateInputLoop);

    console.log(
      "[useCameraControls] Initialized (left-drag pan + edge scroll)"
    );
  }

  function onResize() {
    if (renderer.value) {
      canvasRect = renderer.value.domElement.getBoundingClientRect();
    }
  }

  function dispose() {
    if (!renderer.value) return;

    const domElement = renderer.value.domElement;

    domElement.removeEventListener("mousedown", onMouseDown);
    domElement.removeEventListener("mouseup", onMouseUp);
    domElement.removeEventListener("mousemove", onMouseMove);
    domElement.removeEventListener("mouseenter", onMouseEnter);
    domElement.removeEventListener("mouseleave", onMouseLeave);
    domElement.removeEventListener("contextmenu", onContextMenu);
    domElement.removeEventListener("wheel", onWheel);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    window.removeEventListener("resize", onResize);

    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
    }
    if (panAnimation) {
      cancelAnimationFrame(panAnimation);
    }
  }

  // Initialize when renderer is ready
  watch(renderer, (newRenderer) => {
    if (newRenderer) {
      init();
    }
  });

  onUnmounted(() => {
    dispose();
  });

  return {
    target,
    currentZoom,
    isDragging,
    panTo,
    panToPiece,
    resetCamera,
    panBy,
    zoomBy,
  };
}
