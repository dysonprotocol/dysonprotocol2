/**
 * pathfinding.ts - Movement pathfinding utilities
 *
 * Adjacent moves: 8 directions (including diagonals), cost 0
 * Jump moves: any non-adjacent position, cost dx² + dy²
 */

export interface Vec2 {
  x: number;
  y: number;
}

/**
 * Calculate Manhattan-like path using walk moves (step by step)
 * Returns array of waypoints from start to end (inclusive)
 */
export function calculateWalkPath(from: Vec2, to: Vec2): Vec2[] {
  const path: Vec2[] = [{ ...from }];
  let current = { ...from };

  while (current.x !== to.x || current.y !== to.y) {
    const dx = Math.sign(to.x - current.x);
    const dy = Math.sign(to.y - current.y);

    current = {
      x: current.x + dx,
      y: current.y + dy,
    };
    path.push({ ...current });
  }

  return path;
}

/**
 * Calculate the number of walk moves needed
 * (Chebyshev distance - max of dx and dy)
 */
export function walkMoveCount(from: Vec2, to: Vec2): number {
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  return Math.max(dx, dy);
}

/**
 * Check if a move is a valid jump (any non-adjacent position)
 * Note: All positions are valid jump targets (no line restriction)
 */
export function isJumpMove(from: Vec2, to: Vec2): boolean {
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  // Any non-adjacent move is a jump
  return dx > 1 || dy > 1;
}

/**
 * Calculate jump move cost: dx² + dy²
 * Adjacent moves (dx <= 1 && dy <= 1) return 0
 */
export function jumpMoveCost(from: Vec2, to: Vec2): number {
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  // Adjacent moves are free
  if (dx <= 1 && dy <= 1) return 0;
  return dx * dx + dy * dy;
}

// Backwards compatibility aliases
export const isQueenMove = isJumpMove;
export const queenMoveCost = jumpMoveCost;
export const calculateKingPath = calculateWalkPath;
export const kingMoveCount = walkMoveCount;

/**
 * Check if two positions are adjacent (walk move)
 */
export function isAdjacent(from: Vec2, to: Vec2): boolean {
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  return dx <= 1 && dy <= 1 && (dx > 0 || dy > 0);
}

/**
 * A* pathfinding with obstacle avoidance
 * Returns path from start to goal, or empty array if no path exists
 */
export function findPath(
  start: Vec2,
  goal: Vec2,
  obstacles: Set<string>,
  bounds: { min: number; max: number }
): Vec2[] {
  const key = (p: Vec2) => `${p.x},${p.y}`;
  
  // If start === goal, return single point
  if (start.x === goal.x && start.y === goal.y) {
    return [{ ...start }];
  }
  
  // If goal is an obstacle, no path
  if (obstacles.has(key(goal))) {
    return [];
  }

  interface Node {
    pos: Vec2;
    g: number;  // Cost from start
    f: number;  // g + heuristic
    parent: Node | null;
  }

  // Chebyshev distance heuristic (walk moves)
  const heuristic = (a: Vec2, b: Vec2) => Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));

  const openSet: Node[] = [{ pos: { ...start }, g: 0, f: heuristic(start, goal), parent: null }];
  const closedSet = new Set<string>();

  // 8 directions for walk moves
  const directions = [
    { x: -1, y: -1 }, { x: 0, y: -1 }, { x: 1, y: -1 },
    { x: -1, y: 0 },                    { x: 1, y: 0 },
    { x: -1, y: 1 },  { x: 0, y: 1 },  { x: 1, y: 1 },
  ];

  while (openSet.length > 0) {
    // Get node with lowest f score
    openSet.sort((a, b) => a.f - b.f);
    const current = openSet.shift()!;
    const currentKey = key(current.pos);

    // Found goal
    if (current.pos.x === goal.x && current.pos.y === goal.y) {
      // Reconstruct path
      const path: Vec2[] = [];
      let node: Node | null = current;
      while (node) {
        path.unshift({ ...node.pos });
        node = node.parent;
      }
      return path;
    }

    closedSet.add(currentKey);

    // Check neighbors
    for (const dir of directions) {
      const next: Vec2 = { x: current.pos.x + dir.x, y: current.pos.y + dir.y };
      const nextKey = key(next);

      // Skip if out of bounds
      if (next.x < bounds.min || next.x > bounds.max || next.y < bounds.min || next.y > bounds.max) {
        continue;
      }

      // Skip if obstacle or already visited
      if (obstacles.has(nextKey) || closedSet.has(nextKey)) {
        continue;
      }

      const g = current.g + 1;
      const f = g + heuristic(next, goal);

      // Check if already in open set with better path
      const existing = openSet.find((n) => n.pos.x === next.x && n.pos.y === next.y);
      if (existing) {
        if (g < existing.g) {
          existing.g = g;
          existing.f = f;
          existing.parent = current;
        }
      } else {
        openSet.push({ pos: next, g, f, parent: current });
      }
    }
  }

  // No path found
  return [];
}

