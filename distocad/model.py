import io
import math
import statistics
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from defusedxml import ElementTree as SafeET

MAX_XML_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MEASUREMENT_STEP_M = Decimal("0.0001")


class InputError(Exception):
    pass


@dataclass
class Wall:
    start: tuple[float, float]
    end: tuple[float, float]
    meters: Decimal | None

    @property
    def sketch_length(self):
        return math.dist(self.start, self.end)

    @property
    def sketch_angle(self):
        return math.degrees(math.atan2(self.end[1] - self.start[1], self.end[0] - self.start[0]))


@dataclass
class Polyline:
    index: int
    walls: list

    @property
    def closed(self):
        if len(self.walls) < 3:
            return False
        tolerance = 1e-6
        joins = zip(self.walls, self.walls[1:])
        if not all(math.dist(left.end, right.start) < tolerance for left, right in joins):
            return False
        return math.dist(self.walls[-1].end, self.walls[0].start) < tolerance

    @property
    def measured(self):
        return all(wall.meters is not None for wall in self.walls)


@dataclass
class Sketch:
    name: str
    sketch_type: str
    polylines: list = field(default_factory=list)

    @property
    def mm_per_unit(self):
        ratios = [
            wall.sketch_length / float(wall.meters)
            for polyline in self.polylines
            for wall in polyline.walls
            if wall.meters is not None and wall.sketch_length > 0
        ]
        return 1000.0 / statistics.median(ratios) if ratios else 1.0


def parse_meters(raw):
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value.quantize(MEASUREMENT_STEP_M, rounding=ROUND_HALF_UP)


def to_millimetres(meters: Decimal) -> int:
    return int((meters * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def extract_xml(data):
    if data[:2] != b"PK":
        if len(data) > MAX_XML_BYTES:
            raise InputError("Plik XML jest zbyt duzy")
        return data
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
                raise InputError("Archiwum po rozpakowaniu jest zbyt duze")
            target = next((info for info in infos if info.filename.lower().endswith("distofile.xml")), None)
            if target is None:
                raise InputError("Archiwum nie zawiera pliku DistoFile.xml")
            if target.file_size > MAX_XML_BYTES:
                raise InputError("Plik DistoFile.xml jest zbyt duzy")
            with archive.open(target) as handle:
                return handle.read(MAX_XML_BYTES + 1)
    except zipfile.BadZipFile as error:
        raise InputError("Uszkodzone archiwum .cmi") from error


def read_sketch(data):
    xml = extract_xml(data)
    try:
        root = SafeET.fromstring(xml)
    except Exception as error:
        raise InputError("Plik nie jest poprawnym XML-em DISTO") from error
    if root.tag != "DistoFile":
        raise InputError("To nie jest plik DISTO Plan")

    document = root.find("Documents/Document")
    if document is None:
        raise InputError("Plik nie zawiera planu (to moze byc plik projektu bez szkicow)")

    sketch_node = document.find("Sketch")
    if sketch_node is None:
        raise InputError("Plan nie zawiera szkicu")

    name_node = document.find("Name")
    name = (name_node.text or "").strip() if name_node is not None else ""
    sketch = Sketch(name=name, sketch_type=sketch_node.get("SketchType", ""))

    for index, polygon in enumerate(sketch_node.iter("SketchPolygon"), start=1):
        lines = polygon.find("PolyLines")
        if lines is None:
            continue

        walls = []
        for line in lines:
            start_node = line.find("StartPoint")
            end_node = line.find("EndPoint")
            if start_node is None or end_node is None:
                continue
            try:
                start = (float(start_node.get("X")), float(start_node.get("Y")))
                end = (float(end_node.get("X")), float(end_node.get("Y")))
            except (TypeError, ValueError) as error:
                raise InputError("Niepoprawne wspolrzedne lub pomiar w szkicu") from error
            walls.append(Wall(start, end, parse_meters(line.get("Measurement", ""))))

        if walls:
            sketch.polylines.append(Polyline(index, walls))

    return sketch
