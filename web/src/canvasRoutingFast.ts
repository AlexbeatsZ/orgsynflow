export type RoutingPoint = { x: number; y: number };
export type RoutingRect = { left: number; right: number; top: number; bottom: number };

export function findFastOrthogonalPath(
  start: RoutingPoint,
  end: RoutingPoint,
  obstacles: RoutingRect[],
): RoutingPoint[] {
  if (start.x === end.x || start.y === end.y) return [start, end];
  const middleX = (start.x + end.x) / 2;
  const middleY = (start.y + end.y) / 2;
  const candidates = [
    [start, { x: end.x, y: start.y }, end],
    [start, { x: start.x, y: end.y }, end],
    [start, { x: middleX, y: start.y }, { x: middleX, y: end.y }, end],
    [start, { x: start.x, y: middleY }, { x: end.x, y: middleY }, end],
  ].map(simplifyRoutingPoints);
  const clear = candidates.filter((points) => !isRoutingPathBlocked(points, obstacles));
  const ranked = clear.length > 0 ? clear : candidates;
  ranked.sort(compareRoutingPaths);
  return ranked[0];
}

function isRoutingPathBlocked(points: RoutingPoint[], obstacles: RoutingRect[]): boolean {
  for (let index = 0; index < points.length - 1; index += 1) {
    if (isRoutingSegmentBlocked(points[index], points[index + 1], obstacles)) return true;
  }
  return false;
}

function isRoutingSegmentBlocked(start: RoutingPoint, end: RoutingPoint, rects: RoutingRect[]): boolean {
  if (start.x === end.x) {
    const top = Math.min(start.y, end.y);
    const bottom = Math.max(start.y, end.y);
    return rects.some((rect) => start.x > rect.left && start.x < rect.right && bottom > rect.top && top < rect.bottom);
  }
  const left = Math.min(start.x, end.x);
  const right = Math.max(start.x, end.x);
  return rects.some((rect) => start.y > rect.top && start.y < rect.bottom && right > rect.left && left < rect.right);
}

function compareRoutingPaths(left: RoutingPoint[], right: RoutingPoint[]): number {
  const leftLengths = routingSegmentLengths(left);
  const rightLengths = routingSegmentLengths(right);
  const leftLength = leftLengths.reduce((sum, value) => sum + value, 0);
  const rightLength = rightLengths.reduce((sum, value) => sum + value, 0);
  if (leftLength !== rightLength) return leftLength - rightLength;
  return leftLengths.length - rightLengths.length;
}

function routingSegmentLengths(points: RoutingPoint[]): number[] {
  const lengths: number[] = [];
  for (let index = 1; index < points.length; index += 1) {
    lengths.push(Math.abs(points[index].x - points[index - 1].x) + Math.abs(points[index].y - points[index - 1].y));
  }
  return lengths;
}

function simplifyRoutingPoints(points: RoutingPoint[]): RoutingPoint[] {
  const simplified: RoutingPoint[] = [];
  for (const point of points) {
    const previous = simplified[simplified.length - 1];
    const beforePrevious = simplified[simplified.length - 2];
    if (previous?.x === point.x && previous.y === point.y) continue;
    if (
      beforePrevious && previous &&
      ((beforePrevious.x === previous.x && previous.x === point.x) ||
       (beforePrevious.y === previous.y && previous.y === point.y))
    ) {
      simplified[simplified.length - 1] = point;
    } else {
      simplified.push(point);
    }
  }
  return simplified;
}
