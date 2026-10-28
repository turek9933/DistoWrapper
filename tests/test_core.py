import io
import math
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

import ezdxf

from distocad import InputError, Options, convert_bytes, convert_many
from distocad.model import read_sketch
from distocad.solver import solve
from distocad.testing import make_cmi, rectangle

FIXTURES = Path(__file__).parent / "fixtures"


def load_dxf(data):
    return ezdxf.read(io.StringIO(data.decode("utf-8")))


def polylines(doc, layer="0"):
    return [e for e in doc.modelspace() if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == layer]


def texts(doc):
    return [e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"]


def circles(doc, layer="0"):
    return [e for e in doc.modelspace() if e.dxftype() == "CIRCLE" and e.dxf.layer == layer]


def points(poly):
    return [(round(p[0], 6), round(p[1], 6)) for p in poly.get_points("xy")]


class RectangleTests(unittest.TestCase):
    def test_rectangle_is_open_and_has_area_label(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        result = convert_bytes(data, "a.cmi", Options(version="orthogonal"))
        room = result.report["rooms"][0]
        self.assertEqual(room["status"], "ok")
        self.assertEqual(room["gap"]["distance_mm"], 0.0)
        self.assertAlmostEqual(room["area_m2"], 6.3, places=4)
        self.assertEqual(sorted(result.outputs), ["a.dxf"])
        doc = load_dxf(result.outputs["a.dxf"])
        (poly,) = polylines(doc)
        self.assertFalse(poly.closed)
        self.assertEqual(len(points(poly)), 5)
        self.assertEqual(points(poly)[0], points(poly)[-1])
        self.assertIn("CHECK6.30 m2", texts(doc))
        self.assertIn("a", texts(doc))

    def test_gap_and_right_angles(self):
        data = make_cmi([[(0, 0, 300, 0, 3.15), (300, 0, 300, 200, 2.0), (300, 200, 0, 200, 3.16), (0, 200, 0, 0, 2.005)]])
        result = convert_bytes(data, "a.cmi", Options(version="orthogonal"))
        room = result.report["rooms"][0]
        self.assertAlmostEqual(room["gap"]["dx_mm"], -10.0, places=6)
        self.assertAlmostEqual(room["gap"]["dy_mm"], -5.0, places=6)
        self.assertFalse(room["gap"]["over_threshold"])
        self.assertEqual(room["angles_not_90"], [])
        doc = load_dxf(result.outputs["a.dxf"])
        (poly,) = polylines(doc)
        pts = points(poly)
        for a, b in zip(pts, pts[1:]):
            self.assertTrue(abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9)

    def test_lengths_are_rounded_to_millimetres(self):
        data = make_cmi([[(0, 0, 300, 0, 3.1498999595642), (300, 0, 300, 200, 2.0), (300, 200, 0, 200, 3.1499), (0, 200, 0, 0, 2.0)]])
        result = convert_bytes(data, "a.cmi", Options(version="orthogonal"))
        self.assertEqual(result.report["rooms"][0]["wall_lengths_mm"][0], 3150)

    def test_half_millimetre_rounds_up_after_normalization(self):
        data = make_cmi([rectangle(300, 200, "6.088499546051025", "4.230500221252441")])
        result = convert_bytes(data, "a.cmi", Options(version="orthogonal"))
        self.assertEqual(result.report["rooms"][0]["wall_lengths_mm"], [6089, 4231, 6089, 4231])

    def test_labels_are_optional_in_orthogonal(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        default = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs["a.dxf"])
        with_labels = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal", labels=True)).outputs["a.dxf"])
        self.assertEqual(sorted(texts(default)), ["CHECK6.30 m2", "a"])
        self.assertEqual(len(texts(with_labels)), 6)

    def test_original_always_has_labels_but_no_area_or_title(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        doc = load_dxf(convert_bytes(data, "a.cmi", Options(version="original", labels=False)).outputs["a.dxf"])
        self.assertEqual(len(texts(doc)), 4)
        self.assertFalse(any("m2" in text for text in texts(doc)))
        self.assertNotIn("a", texts(doc))
        self.assertEqual(len(polylines(doc)), 1)

    def test_text_height_is_fixed_at_100(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        doc = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs["a.dxf"])
        for entity in doc.modelspace():
            if entity.dxftype() == "TEXT":
                self.assertEqual(entity.dxf.height, 100.0)

    def test_flat_default_and_optional_layers(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        flat = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs["a.dxf"])
        self.assertTrue(all(e.dxf.layer == "0" for e in flat.modelspace()))
        layered = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal", layers=True, labels=True)).outputs["a.dxf"])
        self.assertEqual(len(polylines(layered, "SCIANY")), 1)
        self.assertEqual(len(polylines(layered, "WYMIARY")), 0)
        self.assertTrue(any(e.dxftype() == "TEXT" and e.dxf.layer == "WYMIARY" for e in layered.modelspace()))
        self.assertTrue(any(e.dxftype() == "TEXT" and e.dxf.layer == "POLA" for e in layered.modelspace()))
        self.assertTrue(any(e.dxftype() == "TEXT" and e.dxf.layer == "TYTUL" for e in layered.modelspace()))

    def test_dxf_version_is_r2010(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        doc = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs["a.dxf"])
        self.assertEqual(doc.dxfversion, "AC1024")

    def test_gap_warning_above_threshold(self):
        data = make_cmi([[(0, 0, 300, 0, 3.15), (300, 0, 300, 200, 2.0), (300, 200, 0, 200, 3.17), (0, 200, 0, 0, 2.01)]])
        result = convert_bytes(data, "a.cmi", Options(version="orthogonal"))
        room = result.report["rooms"][0]
        self.assertTrue(room["gap"]["over_threshold"])
        self.assertAlmostEqual(room["gap"]["distance_mm"], 22.36, places=2)
        doc = load_dxf(result.outputs["a.dxf"])
        self.assertIn("UWAGA, szczelina 22.36 mm", texts(doc))

    def test_no_warning_at_or_below_threshold(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        doc = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs["a.dxf"])
        self.assertFalse(any(text.startswith("UWAGA") for text in texts(doc)))

    def test_gap_circles_are_default_in_orthogonal_only(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        default = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs["a.dxf"])
        self.assertEqual(len(circles(default)), 2)
        self.assertEqual(sorted(round(c.dxf.radius, 3) for c in circles(default)), [1000.0, 1575.0])
        without = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal", gap_circles=False)).outputs["a.dxf"])
        self.assertEqual(circles(without), [])
        original = load_dxf(convert_bytes(data, "a.cmi", Options(version="original", gap_circles=True)).outputs["a.dxf"])
        self.assertEqual(circles(original), [])

    def test_layout_sketch_and_row(self):
        data = make_cmi([rectangle(300, 200, 3.0, 2.0), rectangle(300, 200, 3.0, 2.0, x=1000)])
        sketch = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal", layout="sketch")).outputs["a.dxf"])
        first, second = polylines(sketch)
        self.assertAlmostEqual(min(p[0] for p in points(second)), 10000.0)
        row = load_dxf(convert_bytes(data, "a.cmi", Options(version="orthogonal", layout="row")).outputs["a.dxf"])
        first, second = polylines(row)
        self.assertAlmostEqual(max(p[0] for p in points(first)), 3000.0)
        self.assertAlmostEqual(min(p[0] for p in points(second)), 4000.0)

    def test_name_resolution(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)], name="Mieszkanie 12")
        result = convert_bytes(data, "DistoFile.xml", Options(version="orthogonal"))
        self.assertEqual(sorted(result.outputs), ["Mieszkanie 12.dxf"])
        doc = load_dxf(result.outputs["Mieszkanie 12.dxf"])
        self.assertIn("Mieszkanie 12", texts(doc))
        manual = convert_bytes(data, "a.cmi", Options(version="orthogonal", name="Ręczna nazwa"))
        self.assertEqual(sorted(manual.outputs), ["Ręczna nazwa.dxf"])
        self.assertIn("Ręczna nazwa", texts(load_dxf(manual.outputs["Ręczna nazwa.dxf"])))

    def test_manual_name_rejected_for_many_files(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        with self.assertRaises(ValueError):
            convert_many([("a.cmi", data), ("b.cmi", data)], Options(version="orthogonal", name="x"))

    def test_duplicate_output_names_are_suffixed(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        results, report, produced = convert_many([("a.cmi", data), ("a.cmi", data)], Options(version="orthogonal"))
        self.assertEqual(produced, 2)
        self.assertEqual(sorted(results[0].outputs), ["a.dxf"])
        self.assertEqual(sorted(results[1].outputs), ["a_2.dxf"])
        self.assertEqual(report["summary"]["files"], 2)


class IncompleteTests(unittest.TestCase):
    def setUp(self):
        walls = rectangle(300, 200, 3.0, 2.0)
        walls[1] = walls[1][:4] + ("NaN",)
        self.data = make_cmi([walls])

    def test_partial_room_draws_only_measured_run(self):
        result = convert_bytes(self.data, "a.cmi", Options(version="orthogonal"))
        room = result.report["rooms"][0]
        self.assertEqual(room["status"], "partial")
        self.assertEqual(room["missing_walls"], [2])
        self.assertEqual(room["measured_runs"], [[3, 4, 1]])
        self.assertIsNone(room.get("area_m2"))
        self.assertEqual(room["warnings"][0]["code"], "unmeasured")
        doc = load_dxf(result.outputs["a.dxf"])
        (poly,) = polylines(doc)
        self.assertFalse(poly.closed)
        self.assertEqual(len(points(poly)), 4)
        self.assertEqual(texts(doc), ["a"])
        self.assertFalse(any("m2" in text for text in texts(doc)))

    def test_all_missing_is_skipped_in_orthogonal_but_drawn_in_original(self):
        walls = rectangle(300, 200, 3.0, 2.0)
        data = make_cmi([[wall[:4] + ("NaN",) for wall in walls]])
        orthogonal = convert_bytes(data, "a.cmi", Options(version="orthogonal"))
        self.assertEqual(orthogonal.report["rooms"][0]["status"], "skipped")
        self.assertEqual(orthogonal.outputs, {})
        self.assertTrue(orthogonal.report["errors"])
        original = convert_bytes(data, "a.cmi", Options(version="original", labels=False))
        self.assertEqual(original.report["rooms"][0]["status"], "skipped")
        self.assertEqual(len(polylines(load_dxf(original.outputs["a.dxf"]))), 1)

    def test_original_partial_contains_all_walls(self):
        result = convert_bytes(self.data, "a.cmi", Options(version="original", labels=False))
        doc = load_dxf(result.outputs["a.dxf"])
        (poly,) = polylines(doc)
        self.assertFalse(poly.closed)
        self.assertEqual(len(points(poly)), 5)
        self.assertEqual(len(texts(doc)), 3)
        self.assertFalse(any("m2" in text for text in texts(doc)))


class NonOrthogonalTests(unittest.TestCase):
    def test_single_diagonal_wall(self):
        angles = [0.0, 90.0, 180.0 + math.degrees(math.atan2(3, 4))]
        result = solve([4000.0, 3000.0, 5000.0], angles)
        self.assertEqual(result.free, [2])
        self.assertLess(math.hypot(*result.gap), 1e-6)

    def test_rotated_right_angle_pair(self):
        angles = [0.0, 143.13, -126.87]
        result = solve([5000.0, 4000.0, 3000.0], angles)
        self.assertEqual(result.free, [1, 2])
        self.assertEqual(result.units, 1)
        self.assertLess(math.hypot(*result.gap), 1e-6)
        degrees = {(a, b): d for a, b, d in result.angles}
        self.assertNotIn((2, 3), degrees)

    def test_two_pairs_nearest_sketch(self):
        lengths = [3000.0, 1000.0, 1000.0, 3000.0, 1000.0, 1000.0]
        angles = [0.0, 45.0, 135.0, 180.0, -135.0, -45.0]
        result = solve(lengths, angles)
        self.assertEqual(result.units, 2)
        self.assertLess(math.hypot(*result.gap), 1e-6)

    def test_gap_stays_when_lengths_inconsistent(self):
        angles = [0.0, 90.0, 180.0 + math.degrees(math.atan2(3, 4))]
        result = solve([4000.0, 3000.0, 5020.0], angles)
        self.assertAlmostEqual(math.hypot(*result.gap), 20.0, places=6)


class OriginalVersionTests(unittest.TestCase):
    def test_original_includes_all_lines(self):
        room = [(0, 0, 300, 0, 3.0), (300, 0, 300, 200, 2.0), (300, 200, 0, 200, 3.0), (0, 200, 0, 0, 2.0)]
        single = [(50, 50, 150, 50, 1.0)]
        data = make_cmi([room, single])
        result = convert_bytes(data, "a.cmi", Options(version="both", layers=True))
        self.assertEqual(sorted(result.outputs), ["a_oryginal.dxf", "a_prostopadle.dxf"])
        original = load_dxf(result.outputs["a_oryginal.dxf"])
        self.assertEqual(len(polylines(original, "SCIANY")), 1)
        self.assertEqual(len(polylines(original, "MIEDZYMIARY")), 1)
        self.assertFalse(any("m2" in text for text in texts(original)))
        orthogonal = load_dxf(result.outputs["a_prostopadle.dxf"])
        self.assertEqual(len(polylines(orthogonal, "MIEDZYMIARY")), 0)

    def test_single_version_uses_plain_name(self):
        data = make_cmi([rectangle(300, 200, 3.15, 2.0)])
        self.assertEqual(sorted(convert_bytes(data, "a.cmi", Options(version="orthogonal")).outputs), ["a.dxf"])
        self.assertEqual(sorted(convert_bytes(data, "a.cmi", Options(version="original")).outputs), ["a.dxf"])


class InputTests(unittest.TestCase):
    def test_measurements_are_decimal(self):
        wall = read_sketch(make_cmi([rectangle(300, 200, 3.15, 2.0)])).polylines[0].walls[0]
        self.assertEqual(wall.meters, Decimal("3.15"))

    def test_sketch_on_photo_keeps_y_coordinates(self):
        wall = read_sketch(make_cmi([rectangle(300, 200, 3.0, 2.0)])).polylines[0].walls[1]
        self.assertEqual(wall.start, (300.0, 0.0))
        self.assertEqual(wall.end, (300.0, 200.0))

    def test_project_file_without_plans(self):
        xml = b'<DistoFile Content="Project"><Project/><Scenes/><Measurements/><Documents/></DistoFile>'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("DistoFile.xml", xml)
        result = convert_bytes(buffer.getvalue(), "Project.cmi", Options())
        self.assertEqual(result.outputs, {})
        self.assertIn("nie zawiera planu", result.report["errors"][0])

    def test_entities_are_rejected(self):
        xml = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><DistoFile>&a;</DistoFile>'
        with self.assertRaises(InputError):
            read_sketch(xml)

    def test_garbage_archive(self):
        result = convert_bytes(b"PK\x03\x04garbage", "x.cmi", Options())
        self.assertTrue(result.report["errors"])


class OptionsTests(unittest.TestCase):
    def test_defaults(self):
        options = Options()
        self.assertEqual(options.version, "both")
        self.assertEqual(options.layout, "sketch")
        self.assertEqual(options.text_height, 100.0)
        self.assertEqual(options.gap_threshold, 15.0)
        self.assertFalse(options.labels)
        self.assertTrue(options.gap_circles)

    def test_invalid_values(self):
        with self.assertRaises(ValueError):
            Options(version="x").validate()
        with self.assertRaises(ValueError):
            Options(layout="x").validate()
        with self.assertRaises(ValueError):
            Options(gap_threshold=-1).validate()
        with self.assertRaises(ValueError):
            Options(text_height=0).validate()


class RealDataTests(unittest.TestCase):
    def convert(self, name):
        path = FIXTURES / name
        return convert_bytes(path.read_bytes(), name, Options(version="both"))

    def test_092616(self):
        result = self.convert("Plan 2026-10-15 092616.cmi")
        self.assertFalse(result.report["errors"])
        self.assertEqual(len(result.outputs), 2)
        room = next(r for r in result.report["rooms"] if r["id"] == "P1")
        self.assertEqual(room["status"], "ok")
        self.assertAlmostEqual(room["area_m2"], 32.35, places=2)
        self.assertAlmostEqual(room["gap"]["distance_mm"], 24.70, places=2)
        self.assertTrue(room["gap"]["over_threshold"])
        self.assertEqual(room["wall_lengths_mm"][8], 6089)
        doc = load_dxf(result.outputs["Plan 2026-10-15 092616_prostopadle.dxf"])
        self.assertIn("CHECK32.35 m2", texts(doc))
        self.assertIn("UWAGA, szczelina 24.70 mm", texts(doc))
        self.assertIn("Plan 2026-10-15 092616", texts(doc))
        self.assertTrue(all(not poly.closed for poly in polylines(doc)))

    def test_092718(self):
        result = self.convert("Plan 2026-10-15 092718.cmi")
        room = next(r for r in result.report["rooms"] if r["id"] == "P1")
        self.assertAlmostEqual(room["area_m2"], 23.98, places=2)
        self.assertAlmostEqual(room["gap"]["distance_mm"], 15.81, places=2)
        self.assertTrue(room["gap"]["over_threshold"])

    def test_093215(self):
        result = self.convert("Plan 2026-10-15 093215.cmi")
        room = next(r for r in result.report["rooms"] if r["id"] == "P1")
        self.assertAlmostEqual(room["area_m2"], 24.52, places=2)
        self.assertFalse(room["gap"]["over_threshold"])

    def test_092826_partial_room(self):
        result = self.convert("Plan 2026-10-15 092826.cmi")
        self.assertFalse(result.report["errors"])
        room = next(r for r in result.report["rooms"] if r["id"] == "P1")
        self.assertEqual(room["status"], "partial")
        self.assertEqual(room["missing_walls"], [10, 11])
        self.assertEqual(room["measured_runs"], [[12, 13, 14, 15, 16, 1, 2, 3, 4, 5, 6, 7, 8, 9]])
        self.assertIsNone(room.get("area_m2"))
        doc = load_dxf(result.outputs["Plan 2026-10-15 092826_prostopadle.dxf"])
        self.assertTrue(any(len(points(poly)) == 15 for poly in polylines(doc)))
        self.assertTrue(all(not poly.closed for poly in polylines(doc)))
        self.assertTrue(all(e.dxf.height == 100.0 for e in doc.modelspace() if e.dxftype() == "TEXT"))


if __name__ == "__main__":
    unittest.main()
