import argparse
import json
import sys
from pathlib import Path

from .api import LAYOUTS, VERSIONS, Options, convert_many, make_zip


def collect(paths):
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in (".cmi", ".xml")))
        else:
            files.append(path)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(prog="distocad")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("-o", "--outdir", default="wyniki")
    parser.add_argument("--version", choices=VERSIONS, default="both")
    parser.add_argument("--labels", action="store_true", help="Etykiety dlugosci w wersji prostopadlej (oryginalna zawsze ma etykiety)")
    parser.add_argument("--layout", choices=LAYOUTS, default="sketch")
    parser.add_argument("--gap-threshold", type=float, default=15.0)
    parser.add_argument("--gap-circles", dest="gap_circles", action="store_true", default=True)
    parser.add_argument("--no-gap-circles", dest="gap_circles", action="store_false")
    parser.add_argument("--layers", action="store_true")
    parser.add_argument("--free-limit", type=float, default=25.0)
    parser.add_argument("--spacing", type=float, default=1000.0)
    parser.add_argument("--no-title", action="store_true")
    parser.add_argument("--name")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args(argv)

    options = Options(
        version=args.version,
        labels=args.labels,
        layout=args.layout,
        gap_threshold=args.gap_threshold,
        gap_circles=args.gap_circles,
        layers=args.layers,
        free_limit=args.free_limit,
        spacing=args.spacing,
        title=not args.no_title,
        name=args.name,
    )
    files = collect(args.inputs)
    if not files:
        print("Brak plikow wejsciowych", file=sys.stderr)
        return 2
    if args.name and len(files) > 1:
        print("Nazwa reczna jest mozliwa tylko dla jednego pliku", file=sys.stderr)
        return 2
    try:
        results, report, produced = convert_many([(f.name, f.read_bytes()) for f in files], options)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if args.zip:
        (outdir / "wyniki.zip").write_bytes(make_zip(results, report))
    else:
        for result in results:
            for name, data in result.outputs.items():
                (outdir / name).write_bytes(data)
        (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print(f"Wykonano: {summary['files_with_output']}/{summary['files']} plikow, {produced} rysunkow. Raport: report.json")
    for entry in report["files"]:
        for message in entry["errors"]:
            print(f"{entry['file']}: {message}", file=sys.stderr)
        for room in entry.get("rooms", []):
            for item in room["warnings"]:
                print(f"{entry['file']} {room['id']}: {item['message']}", file=sys.stderr)
    return 0 if produced else 1
