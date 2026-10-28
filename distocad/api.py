import io
import json
import math
import os
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import build
from .model import InputError, Polyline, read_sketch, to_millimetres
from .solver import SolveError, label_point, self_intersections, signed_area, solve

VERSIONS = ("orthogonal", "original", "both")
LAYOUTS = ("sketch", "row")


@dataclass
class Options:
    version: str = "both"
    labels: bool = False
    layout: str = "sketch"
    gap_threshold: float = 15.0
    gap_circles: bool = True
    layers: bool = False
    text_height: float = 100.0
    title: bool = True
    free_limit: float = 25.0
    spacing: float = 1000.0
    name: str | None = None

    def validate(self):
        if self.version not in VERSIONS:
            raise ValueError("Niepoprawna wersja rysunku")
        if self.layout not in LAYOUTS:
            raise ValueError("Niepoprawny uklad pomieszczen")
        if self.gap_threshold < 0:
            raise ValueError("Prog szczeliny nie moze byc ujemny")
        if self.spacing < 0:
            raise ValueError("Odstep miedzy pomieszczeniami nie moze byc ujemny")
        if self.text_height <= 0:
            raise ValueError("Wysokosc tekstu musi byc dodatnia")


@dataclass
class Room:
    index: int
    polyline: Polyline
    lengths: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    runs: list = field(default_factory=list)
    status: str = "ok"
    rect: object = None
    warnings: list = field(default_factory=list)

    @property
    def drawn(self):
        return self.rect is not None or bool(self.runs)

    @property
    def gap_distance(self):
        return math.hypot(*self.rect.gap) if self.rect else 0.0


@dataclass
class FileResult:
    filename: str
    outputs: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)


def warning(code, message, **extra):
    return {"code": code, "message": message, **extra}


def wall_lengths_mm(walls):
    return [None if wall.meters is None else to_millimetres(wall.meters) for wall in walls]


def snapped_angle(angle, free_limit):
    k = int(round(angle / 90.0)) % 4
    deviation = abs((angle - k * 90.0 + 180.0) % 360.0 - 180.0)
    return k * 90.0 if deviation <= free_limit else angle


def measured_runs(count, missing):
    missing_set = set(missing)
    if len(missing_set) >= count:
        return []
    runs = []
    for start in range(count):
        if start in missing_set or (start - 1) % count not in missing_set:
            continue
        run, current = [], start
        while current not in missing_set:
            run.append(current)
            current = (current + 1) % count
            if current == start:
                break
        runs.append(run)
    return runs


def analyze(sketch, options):
    rooms = []
    for polyline in sketch.polylines:
        if not polyline.closed:
            continue
        room = Room(polyline.index, polyline)
        room.lengths = wall_lengths_mm(polyline.walls)
        missing = [i for i, length in enumerate(room.lengths) if length is None]
        if missing:
            room.missing = missing
            room.runs = measured_runs(len(polyline.walls), missing)
            room.status = "partial" if room.runs else "skipped"
            room.warnings.append(
                warning("unmeasured", "Brak pomiaru dla scian: " + ", ".join(str(i + 1) for i in missing), walls=[i + 1 for i in missing])
            )
            rooms.append(room)
            continue
        try:
            room.rect = solve(room.lengths, [wall.sketch_angle for wall in polyline.walls], options.free_limit)
        except SolveError as error:
            room.status = "skipped"
            room.warnings.append(warning("unsolvable", f"Nie da sie wyznaczyc ksztaltu: {error}"))
            rooms.append(room)
            continue

        rect = room.rect
        if rect.units >= 3:
            room.warnings.append(
                warning("underdetermined", "Trzy lub wiecej grup scian nieortogonalnych: katy dobrane najblizej szkicu, wynik jest tylko jednym z mozliwych")
            )
        for item in rect.warnings:
            if item.startswith("reversal:"):
                room.warnings.append(warning("reversal", f"Sciany {item.split(':')[1]} biegna w przeciwnych kierunkach"))
        if self_intersections(rect.points):
            room.warnings.append(warning("self_intersection", "Obrys po wyprostowaniu przecina sam siebie"))
        if room.gap_distance > options.gap_threshold:
            room.warnings.append(
                warning("gap", f"Szczelina {room.gap_distance:.2f} mm przekracza prog {options.gap_threshold:g} mm")
            )
        rooms.append(room)
    return rooms


def room_chains(room, sketch, options):
    walls = room.polyline.walls
    scale = sketch.mm_per_unit
    if room.rect:
        anchor = walls[room.rect.opened].start
        ax, ay = anchor[0] * scale, anchor[1] * scale
        points = [(x + ax, y + ay) for x, y in room.rect.points]
        texts = [build.format_length(room.lengths[i]) for i in room.rect.order]
        return [(points, texts, True)]
    chains = []
    for run in room.runs:
        anchor = walls[run[0]].start
        start = (anchor[0] * scale, anchor[1] * scale)
        angles = [snapped_angle(walls[i].sketch_angle, options.free_limit) for i in run]
        lengths = [room.lengths[i] for i in run]
        points = chain_points(start, angles, lengths)
        texts = [build.format_length(room.lengths[i]) for i in run]
        chains.append((points, texts, False))
    return chains


def draw_orthogonal(sketch, rooms, options, title):
    doc = build.new_document(flat=not options.layers)
    msp = doc.modelspace()
    flat = not options.layers
    wall_layer = build.layer_name(build.LAYER_WALLS, flat)
    label_layer = build.layer_name(build.LAYER_LABELS, flat)
    area_layer = build.layer_name(build.LAYER_AREAS, flat)
    helper_layer = build.layer_name(build.LAYER_HELPERS, flat)
    warning_layer = build.layer_name(build.LAYER_WARNINGS, flat)
    title_layer = build.layer_name(build.LAYER_TITLE, flat)

    entries = []
    for room in rooms:
        if not room.drawn:
            continue
        chains = room_chains(room, sketch, options)
        if chains:
            entries.append((room, chains))
    if not entries:
        return doc, 0

    if options.layout == "row":
        cursor = 0.0
        placed = []
        for room, chains in entries:
            points_all = [point for points, _, _ in chains for point in points]
            min_x = min(p[0] for p in points_all)
            max_x = max(p[0] for p in points_all)
            min_y = min(p[1] for p in points_all)
            dx, dy = cursor - min_x, -min_y
            moved = [([(x + dx, y + dy) for x, y in points], texts, full) for points, texts, full in chains]
            placed.append((room, moved))
            cursor += (max_x - min_x) + options.spacing
        entries = placed
    else:
        points_all = [point for _, chains in entries for points, _, _ in chains for point in points]
        dx = -min(p[0] for p in points_all)
        dy = -min(p[1] for p in points_all)
        entries = [
            (room, [([(x + dx, y + dy) for x, y in points], texts, full) for points, texts, full in chains])
            for room, chains in entries
        ]

    drawn_points = []
    count = 0
    for room, chains in entries:
        for points, texts, full in chains:
            build.add_chain(msp, points, wall_layer)
            drawn_points.extend(points)
            count += 1
            if options.labels and texts:
                side = build.interior_side(points)
                build.label_chain(msp, points, texts, options.text_height, side, label_layer)
            if not full:
                continue
            area = abs(signed_area(points)) / 1e6
            build.add_area_label(msp, label_point(points), build.format_area(area), options.text_height, area_layer)
            if room.rect:
                if room.gap_distance > options.gap_threshold:
                    build.add_gap_warning(msp, points, room.gap_distance, options.text_height, warning_layer)
                if options.gap_circles:
                    build.add_gap_circles(msp, points, helper_layer)

    if options.title and drawn_points:
        min_x = min(p[0] for p in drawn_points)
        max_y = max(p[1] for p in drawn_points)
        build.add_title(msp, (min_x, max_y + 500.0), title, options.text_height, title_layer)
    return doc, count


def chain_points(start, angles, lengths):
    points = [start]
    for angle, length in zip(angles, lengths):
        x, y = points[-1]
        points.append((x + length * math.cos(math.radians(angle)), y + length * math.sin(math.radians(angle))))
    return points


def draw_original(sketch, rooms, options):
    doc = build.new_document(flat=not options.layers)
    msp = doc.modelspace()
    flat = not options.layers
    wall_layer = build.layer_name(build.LAYER_WALLS, flat)
    other_layer = build.layer_name(build.LAYER_OTHER, flat)
    label_layer = build.layer_name(build.LAYER_LABELS, flat)
    scale = sketch.mm_per_unit
    height = options.text_height
    drawn = {r.index: r for r in rooms if r.rect}
    count = 0
    for polyline in sketch.polylines:
        walls = polyline.walls
        room = drawn.get(polyline.index)
        if room:
            rect = room.rect
            first = rect.opened
            order = rect.order
            start = (walls[first].start[0] * scale, walls[first].start[1] * scale)
            points = chain_points(start, [walls[i].sketch_angle for i in order], [room.lengths[i] for i in order])
            build.add_chain(msp, points, wall_layer)
            texts = [build.format_length(room.lengths[i]) for i in order]
            build.label_chain(msp, points, texts, height, build.interior_side(points), label_layer)
            count += 1
            continue
        lengths = [
            wall.sketch_length * scale if wall.meters is None else to_millimetres(wall.meters)
            for wall in walls
        ]
        start = (walls[0].start[0] * scale, walls[0].start[1] * scale)
        points = chain_points(start, [wall.sketch_angle for wall in walls], lengths)
        build.add_chain(msp, points, wall_layer if polyline.closed else other_layer)
        for i, wall in enumerate(walls):
            if wall.meters is not None:
                build.add_wall_label(msp, points[i], points[i + 1], build.format_length(lengths[i]), height, 1.0, label_layer)
        count += 1
    return doc, count


def other_lines(sketch):
    singles, pairs, rest = 0, [], 0
    for polyline in sketch.polylines:
        if polyline.closed:
            continue
        if len(polyline.walls) == 1:
            singles += 1
        elif len(polyline.walls) == 2:
            a, b = polyline.walls
            turn = abs((b.sketch_angle - a.sketch_angle + 180.0) % 360.0 - 180.0)
            pairs.append(
                {
                    "id": f"P{polyline.index}",
                    "lengths_mm": wall_lengths_mm(polyline.walls),
                    "right_angle_in_sketch": abs(turn - 90.0) <= 20.0,
                }
            )
        else:
            rest += 1
    return {"single_measurements": singles, "two_line_polylines": pairs, "longer_open_polylines": rest}


def room_report(room, options):
    entry = {
        "id": f"P{room.index}",
        "status": room.status,
        "walls": len(room.polyline.walls),
        "missing_walls": [i + 1 for i in room.missing],
        "measured_runs": [[i + 1 for i in run] for run in room.runs],
    }
    if room.rect:
        rect = room.rect
        points = rect.points
        distance = room.gap_distance
        n = len(room.polyline.walls)
        entry.update(
            {
                "area_m2": round(abs(signed_area(points)) / 1e6, 2),
                "perimeter_mm": sum(room.lengths),
                "wall_lengths_mm": room.lengths,
                "gap": {
                    "dx_mm": round(rect.gap[0], 2),
                    "dy_mm": round(rect.gap[1], 2),
                    "distance_mm": round(distance, 2),
                    "over_threshold": distance > options.gap_threshold,
                    "warning": distance > options.gap_threshold,
                },
                "opened_between_walls": [(rect.opened - 1) % n + 1, rect.opened + 1],
                "non_orthogonal_walls": [i + 1 for i in rect.free],
                "non_orthogonal_groups": rect.units,
                "angles_not_90": [{"walls": [a, b], "degrees": d} for a, b, d in rect.angles],
            }
        )
    else:
        entry["wall_lengths_mm"] = room.lengths
    entry["warnings"] = room.warnings
    return entry


def safe_name(value):
    value = os.path.basename(str(value or "")).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\.dxf$", "", value, flags=re.IGNORECASE)
    value = value.strip(" .")
    return value or "plan"


def resolve_name(filename, sketch, override=None):
    if override:
        return safe_name(override)
    stem = os.path.splitext(os.path.basename(filename))[0] or "plan"
    if stem.lower() == "distofile" and sketch.name:
        return safe_name(sketch.name)
    return safe_name(stem)


def convert_bytes(data, filename, options=None):
    options = options or Options()
    options.validate()
    result = FileResult(filename)
    report = {"file": os.path.basename(filename), "outputs": [], "errors": []}
    result.report = report
    try:
        sketch = read_sketch(data)
    except InputError as error:
        report["errors"].append(str(error))
        return result

    name = resolve_name(filename, sketch, options.name)
    rooms = analyze(sketch, options)
    report["name"] = name
    report["document"] = {"name": sketch.name, "sketch_type": sketch.sketch_type}
    report["rooms"] = [room_report(r, options) for r in rooms]
    report["other_lines"] = other_lines(sketch)

    both = options.version == "both"
    jobs = []
    if options.version in ("orthogonal", "both"):
        jobs.append(("orthogonal", f"{name}_prostopadle.dxf" if both else f"{name}.dxf"))
    if options.version in ("original", "both"):
        jobs.append(("original", f"{name}_oryginal.dxf" if both else f"{name}.dxf"))

    for kind, output_name in jobs:
        if kind == "orthogonal":
            doc, count = draw_orthogonal(sketch, rooms, options, name)
            if count == 0:
                report["errors"].append("Brak pomieszczen do narysowania (zamkniete wielokaty z pomiarami)")
                continue
        else:
            doc, count = draw_original(sketch, rooms, options)
            if count == 0:
                report["errors"].append("Szkic nie zawiera zadnych linii")
                continue
        result.outputs[output_name] = build.to_bytes(doc)
        report["outputs"].append(output_name)
    return result


def convert_many(items, options=None):
    options = options or Options()
    if options.name and len(items) > 1:
        raise ValueError("Nazwa reczna jest mozliwa tylko dla jednego pliku")
    results = [convert_bytes(data, filename, options) for filename, data in items]
    taken = set()
    for result in results:
        renamed = {}
        for name, data in result.outputs.items():
            final, counter = name, 2
            while final in taken:
                base, ext = os.path.splitext(name)
                final = f"{base}_{counter}{ext}"
                counter += 1
            taken.add(final)
            renamed[final] = data
        result.outputs = renamed
        result.report["outputs"] = list(renamed)
    report = build_report(results, options)
    produced = sum(len(r.outputs) for r in results)
    return results, report, produced


def make_zip(results, report):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for result in results:
            for name, data in result.outputs.items():
                z.writestr(name, data)
        z.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))
    return archive.getvalue()


def build_report(results, options):
    files = [r.report for r in results]
    rooms = [room for f in files for room in f.get("rooms", [])]
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "options": asdict(options),
        "summary": {
            "files": len(files),
            "files_with_output": sum(1 for f in files if f["outputs"]),
            "files_with_errors": sum(1 for f in files if f["errors"]),
            "rooms": len(rooms),
            "rooms_partial": sum(1 for r in rooms if r["status"] == "partial"),
            "rooms_skipped": sum(1 for r in rooms if r["status"] == "skipped"),
            "rooms_gap_over_threshold": sum(1 for r in rooms if r.get("gap", {}).get("over_threshold")),
            "rooms_with_warnings": sum(1 for r in rooms if r["warnings"]),
        },
        "files": files,
    }
