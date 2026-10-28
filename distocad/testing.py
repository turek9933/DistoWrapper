import io
import zipfile


def make_cmi(polygons, sketch_type="SketchOnPhoto", name="test"):
    body = []
    for polygon in polygons:
        lines = "".join(
            f'<SketchLine Measurement="{m}"><StartPoint X="{x1}" Y="{y1}" Z="0"/><EndPoint X="{x2}" Y="{y2}" Z="0"/></SketchLine>'
            for x1, y1, x2, y2, m in polygon
        )
        body.append(f"<SketchPolygon><PolyLines>{lines}</PolyLines></SketchPolygon>")
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<DistoFile DistoFileVersion="1.5" CreatorApp="Not defined" Content="Plan"><Scenes/><Measurements/>'
        f'<Documents><Document><Id><Id>00000000-0000-0000-0000-000000000001</Id></Id><Name>{name}</Name>'
        f'<Sketch SketchType="{sketch_type}"><Polygons>{"".join(body)}</Polygons></Sketch></Document></Documents></DistoFile>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("DistoFile.xml", xml)
    return buffer.getvalue()


def rectangle(width_px, height_px, width_m, height_m, x=0, y=0):
    return [
        (x, y, x + width_px, y, width_m),
        (x + width_px, y, x + width_px, y + height_px, height_m),
        (x + width_px, y + height_px, x, y + height_px, width_m),
        (x, y + height_px, x, y, height_m),
    ]
