import io
import math

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .solver import signed_area

LAYER_WALLS = "SCIANY"
LAYER_OTHER = "MIEDZYMIARY"
LAYER_LABELS = "WYMIARY"
LAYER_AREAS = "POLA"
LAYER_HELPERS = "POMOCNICZE"
LAYER_WARNINGS = "OSTRZEZENIA"
LAYER_TITLE = "TYTUL"

LAYERS = (LAYER_WALLS, LAYER_OTHER, LAYER_LABELS, LAYER_AREAS, LAYER_HELPERS, LAYER_WARNINGS, LAYER_TITLE)
LAYER_COLORS = {
    LAYER_WALLS: 7,
    LAYER_OTHER: 8,
    LAYER_LABELS: 3,
    LAYER_AREAS: 5,
    LAYER_HELPERS: 4,
    LAYER_WARNINGS: 1,
    LAYER_TITLE: 2,
}


def new_document(flat=True):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    if not flat:
        for name in LAYERS:
            doc.layers.add(name, color=LAYER_COLORS[name])
    return doc


def layer_name(name, flat):
    return "0" if flat else name


def to_bytes(doc):
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode(doc.output_encoding)


def format_length(value):
    return f"{round(value):d}"


def format_area(value):
    return f"CHECK{value:.2f} m2"


def clean(point):
    return (round(point[0], 4), round(point[1], 4))


def add_wall_label(msp, a, b, text, height, side, layer=LAYER_LABELS):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy * side, ux * side
    offset = 0.7 * height
    position = ((a[0] + b[0]) / 2 + nx * offset, (a[1] + b[1]) / 2 + ny * offset)
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90 or angle <= -90:
        angle += 180
    entity = msp.add_text(text, height=height, dxfattribs={"layer": layer, "rotation": angle})
    entity.set_placement(position, align=TextEntityAlignment.MIDDLE_CENTER)


def add_area_label(msp, point, text, height, layer=LAYER_AREAS):
    entity = msp.add_text(text, height=height, dxfattribs={"layer": layer})
    entity.set_placement(point, align=TextEntityAlignment.MIDDLE_CENTER)


def add_warning_label(msp, point, text, height, layer=LAYER_WARNINGS):
    entity = msp.add_text(text, height=height, dxfattribs={"layer": layer})
    entity.set_placement(point, align=TextEntityAlignment.MIDDLE_LEFT)


def add_title(msp, point, text, height, layer=LAYER_TITLE):
    entity = msp.add_text(text, height=height, dxfattribs={"layer": layer})
    entity.set_placement(point, align=TextEntityAlignment.MIDDLE_LEFT)


def add_chain(msp, points, layer):
    msp.add_lwpolyline([clean(p) for p in points], dxfattribs={"layer": layer})


def add_gap_circles(msp, points, layer=LAYER_HELPERS):
    for a, b in ((points[0], points[1]), (points[-2], points[-1])):
        length = math.dist(a, b)
        if length < 1e-9:
            continue
        center = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        msp.add_circle(center, length / 2.0, dxfattribs={"layer": layer})


def add_gap_warning(msp, points, distance, height, layer=LAYER_WARNINGS):
    a, b = points[0], points[-1]
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    dx, dy = mid[0] - cx, mid[1] - cy
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        dx, dy, norm = 0.0, 1.0, 1.0
    offset = 1.5 * height
    position = (mid[0] + dx / norm * offset, mid[1] + dy / norm * offset)
    add_warning_label(msp, position, f"UWAGA, szczelina {distance:.2f} mm", height, layer)


def interior_side(points):
    return 1.0 if signed_area(points) >= 0 else -1.0


def label_chain(msp, points, texts, height, side, layer=LAYER_LABELS):
    for i, text in enumerate(texts):
        add_wall_label(msp, points[i], points[i + 1], text, height, side, layer)
