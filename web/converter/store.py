import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from django.conf import settings

TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


def root():
    path = Path(settings.DISTO_EPHEMERAL_DIR)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def valid(token):
    return bool(TOKEN.match(token or ""))


def folder(token):
    if not valid(token):
        raise FileNotFoundError(token)
    return root() / token


def purge():
    limit = time.time() - settings.DISTO_EPHEMERAL_TTL
    for entry in root().iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < limit:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            continue


def create():
    token = secrets.token_urlsafe(24)
    folder(token).mkdir(mode=0o700)
    return token


def save_outputs(token, zip_bytes, outputs, report):
    base = folder(token)
    outdir = base / "out"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(mode=0o700)
    names = []
    for name, data in outputs.items():
        safe = os.path.basename(name)
        if not safe or safe in names:
            continue
        (outdir / safe).write_bytes(data)
        names.append(safe)
    (base / "wyniki.zip").write_bytes(zip_bytes)
    (base / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "outputs.json").write_text(json.dumps(names), encoding="utf-8")
    (base / "summary.json").write_text(json.dumps(report["summary"]), encoding="utf-8")
    os.utime(base)


def read_bytes(token, name):
    path = folder(token) / name
    return path.read_bytes() if path.exists() else None


def output_names(token):
    raw = read_bytes(token, "outputs.json")
    return json.loads(raw) if raw else []


def read_output(token, name):
    if name not in output_names(token):
        return None
    path = folder(token) / "out" / name
    return path.read_bytes() if path.exists() else None


def exists(token):
    return valid(token) and (root() / token).is_dir()
