import math
from dataclasses import dataclass, field

AXES = ((1, 0), (0, 1), (-1, 0), (0, -1))


class SolveError(Exception):
    pass


@dataclass
class Rectified:
    points: list
    order: list
    opened: int
    gap: tuple
    free: list
    units: int
    vectors: list
    angles: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _rot(v, phi):
    c, s = math.cos(phi), math.sin(phi)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])


def _wrap(angle):
    return (angle + 180.0) % 360.0 - 180.0


def _units(free, angles, free_limit, n):
    free_set = set(free)
    runs, seen = [], set()
    for i in range(n):
        if i in free_set and (i - 1) % n not in free_set:
            run, j = [], i
            while j in free_set and j not in seen:
                run.append(j)
                seen.add(j)
                j = (j + 1) % n
            runs.append(run)
    units = []
    for run in runs:
        current, qs = [run[0]], {run[0]: 0}
        for e in run[1:]:
            p = current[-1]
            rel = _wrap(angles[e] - angles[p])
            q = int(round(rel / 90.0))
            if abs(rel - 90.0 * q) > free_limit:
                units.append((current, qs))
                current, qs = [e], {e: 0}
            else:
                current.append(e)
                qs[e] = (qs[p] + q) % 4
        units.append((current, qs))
    return units


def _solve_rotations(units, lengths, angles, target):
    blocks = []
    for edges, qs in units:
        w = [0.0, 0.0]
        for e in edges:
            ax = AXES[qs[e]]
            w[0] += lengths[e] * ax[0]
            w[1] += lengths[e] * ax[1]
        blocks.append((w[0], w[1]))
    phi = [math.radians(angles[edges[0]]) for edges, _ in units]

    if len(units) == 1:
        w = blocks[0]
        if math.hypot(*target) > 1e-9 and math.hypot(*w) > 1e-9:
            phi[0] = math.atan2(target[1], target[0]) - math.atan2(w[1], w[0])
        return phi

    scale = sum(math.hypot(*w) ** 2 for w in blocks) or 1.0
    best, best_norm = list(phi), None
    for _ in range(300):
        total = [0.0, 0.0]
        cols = []
        for w, p in zip(blocks, phi):
            r = _rot(w, p)
            total[0] += r[0]
            total[1] += r[1]
            cols.append(_rot(w, p + math.pi / 2))
        fx, fy = total[0] - target[0], total[1] - target[1]
        norm = math.hypot(fx, fy)
        if best_norm is None or norm < best_norm:
            best, best_norm = list(phi), norm
        if norm < 1e-9:
            break
        a = sum(c[0] * c[0] for c in cols) + 1e-9 * scale
        b = sum(c[0] * c[1] for c in cols)
        d = sum(c[1] * c[1] for c in cols) + 1e-9 * scale
        det = a * d - b * b
        if abs(det) < 1e-18:
            break
        y0 = (d * fx - b * fy) / det
        y1 = (-b * fx + a * fy) / det
        steps = [-(c[0] * y0 + c[1] * y1) for c in cols]
        peak = max(abs(s) for s in steps)
        if peak > 0.5:
            steps = [s * 0.5 / peak for s in steps]
        phi = [p + s for p, s in zip(phi, steps)]
    return best


def solve(lengths, angles, free_limit=20.0):
    n = len(lengths)
    axis, deviation = [], []
    for a in angles:
        k = int(round(a / 90.0)) % 4
        axis.append(k)
        deviation.append(abs(_wrap(a - k * 90.0)))
    free = [i for i in range(n) if deviation[i] > free_limit]
    if len(free) >= n:
        raise SolveError("zbyt wiele scian nieortogonalnych")

    vectors = [None] * n
    for i in range(n):
        if i not in free:
            ax = AXES[axis[i]]
            vectors[i] = (ax[0] * lengths[i], ax[1] * lengths[i])

    warnings = []
    units = _units(free, angles, free_limit, n)
    if units:
        target = (-sum(v[0] for v in vectors if v), -sum(v[1] for v in vectors if v))
        phi = _solve_rotations(units, lengths, angles, target)
        for (edges, qs), p in zip(units, phi):
            for e in edges:
                ax = AXES[qs[e]]
                vectors[e] = _rot((ax[0] * lengths[e], ax[1] * lengths[e]), p)
        if len(units) >= 3:
            warnings.append("underdetermined")

    for i in range(n):
        j = (i + 1) % n
        if i not in free and j not in free and (axis[j] - axis[i]) % 4 == 2:
            warnings.append(f"reversal:{i + 1}-{j + 1}")

    sums = [lengths[i - 1] + lengths[i] for i in range(n)]
    opened = max(range(n), key=lambda i: sums[i])
    order = list(range(opened, n)) + list(range(opened))
    points = [(0.0, 0.0)]
    for i in order:
        x, y = points[-1]
        points.append((x + vectors[i][0], y + vectors[i][1]))
    gap = (points[-1][0] - points[0][0], points[-1][1] - points[0][1])

    angles_out = []
    orientation = 1.0 if signed_area(points) >= 0 else -1.0
    for i in range(1, n):
        a, b, c = points[i - 1], points[i], points[i + 1]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        turn = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]))
        interior = 180.0 - turn if orientation > 0 else 180.0 + turn
        if abs(interior - 90.0) > 1e-6 and abs(interior - 270.0) > 1e-6:
            angles_out.append((order[i - 1] + 1, order[i] + 1, round(interior, 4)))

    return Rectified(points, order, opened, gap, free, len(units), vectors, angles_out, warnings)


def signed_area(points):
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _cross(o, p, q):
    return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])


def self_intersections(points):
    segments = [(points[i], points[i + 1]) for i in range(len(points) - 1)]
    found = []
    for i in range(len(segments)):
        for j in range(i + 2, len(segments)):
            if i == 0 and j == len(segments) - 1:
                continue
            a, b = segments[i]
            c, d = segments[j]
            if _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0:
                found.append((i, j))
    return found


def _inside(point, polygon):
    x, y = point
    result = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            result = not result
    return result


def _edge_distance(point, polygon):
    best = float("inf")
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2))
        best = min(best, math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy))
    return best


def label_point(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    best, best_d = ((x0 + x1) / 2, (y0 + y1) / 2), -1.0
    for _ in range(3):
        steps = 24
        for i in range(steps + 1):
            for j in range(steps + 1):
                p = (x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * j / steps)
                if _inside(p, points):
                    d = _edge_distance(p, points)
                    if d > best_d:
                        best, best_d = p, d
        w, h = (x1 - x0) / 4, (y1 - y0) / 4
        x0, x1, y0, y1 = best[0] - w, best[0] + w, best[1] - h, best[1] + h
    return best
