import hmac
import io
import json
import zipfile
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from distocad import convert_many, make_zip

from . import store
from .forms import ConvertForm

MAX_TOKENS_PER_SESSION = 10


def client_ip(request):
    return request.META.get(settings.DISTO_CLIENT_IP_HEADER) or request.META.get("REMOTE_ADDR", "unknown")


def rate_limited(request):
    if settings.DISTO_RATE_LIMIT <= 0:
        return False
    key = f"rate:{client_ip(request)}"
    if cache.add(key, 1, timeout=settings.DISTO_RATE_WINDOW):
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=settings.DISTO_RATE_WINDOW)
        return False
    return count > settings.DISTO_RATE_LIMIT


def password_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if settings.DISTO_PASSWORD and not request.session.get("disto_authenticated"):
            return redirect("converter:login")
        return view(request, *args, **kwargs)

    return wrapper


def owned(request, token):
    if token not in request.session.get("tokens", []) or not store.exists(token):
        raise Http404
    return token


def run(request, items, options):
    results, report, produced = convert_many(items, options)
    outputs = {}
    for result in results:
        outputs.update(result.outputs)
    token = store.create()
    store.save_outputs(token, make_zip(results, report), outputs, report)
    tokens = [t for t in request.session.get("tokens", []) if t != token] + [token]
    request.session["tokens"] = tokens[-MAX_TOKENS_PER_SESSION:]
    return redirect("converter:result", token=token)


@require_http_methods(["GET", "POST"])
def login(request):
    if not settings.DISTO_PASSWORD or request.session.get("disto_authenticated"):
        return redirect("converter:index")
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.POST.get("password", "").encode("utf-8"), settings.DISTO_PASSWORD.encode("utf-8")):
            request.session["disto_authenticated"] = True
            return redirect("converter:index")
        error = "Nieprawidłowe hasło"
    return render(request, "converter/login.html", {"error": error})


@require_http_methods(["GET", "POST"])
@password_required
def index(request):
    store.purge()
    if request.method == "POST":
        if rate_limited(request):
            return render(request, "converter/index.html", {"form": ConvertForm(), "limit_error": True}, status=429)
        form = ConvertForm(request.POST, request.FILES)
        if form.is_valid():
            items = [(f.name, f.read()) for f in form.cleaned_data["files"]]
            return run(request, items, form.options())
        return render(request, "converter/index.html", {"form": form}, status=400)
    return render(request, "converter/index.html", {"form": ConvertForm()})


def summarize(report):
    files = []
    for entry in report["files"]:
        messages = list(entry["errors"])
        for room in entry.get("rooms", []):
            for item in room["warnings"]:
                messages.append(f"{room['id']}: {item['message']}")
        files.append({"name": entry["file"], "outputs": entry["outputs"], "messages": messages})
    return files


@require_GET
@password_required
def result(request, token):
    store.purge()
    try:
        owned(request, token)
    except Http404:
        return render(request, "converter/expired.html", status=404)
    report = json.loads(store.read_bytes(token, "report.json"))
    files = summarize(report)
    single = len(report["files"]) == 1
    outputs = [name for entry in files for name in entry["outputs"]]
    has_both = single and any(name.endswith("_prostopadle.dxf") for name in outputs) and any(
        name.endswith("_oryginal.dxf") for name in outputs
    )
    context = {
        "token": token,
        "summary": report["summary"],
        "files": files,
        "single": single,
        "has_both": has_both,
        "produced": sum(len(f["outputs"]) for f in files),
    }
    return render(request, "converter/result.html", context)


@require_GET
@password_required
def download(request, token, kind):
    owned(request, token)
    if kind == "zip":
        data, name, mime = store.read_bytes(token, "wyniki.zip"), "wyniki.zip", "application/zip"
    elif kind == "report":
        data, name, mime = store.read_bytes(token, "report.json"), "report.json", "application/json"
    else:
        raise Http404
    if data is None:
        raise Http404
    response = FileResponse(io.BytesIO(data), as_attachment=True, filename=name, content_type=mime)
    response["Cache-Control"] = "no-store"
    return response


@require_GET
@password_required
def download_both(request, token):
    owned(request, token)
    names = store.output_names(token)
    orthogonal = [name for name in names if name.endswith("_prostopadle.dxf")]
    original = [name for name in names if name.endswith("_oryginal.dxf")]
    if len(orthogonal) != 1 or len(original) != 1:
        raise Http404
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in (orthogonal[0], original[0]):
            data = store.read_output(token, name)
            if data is None:
                raise Http404
            archive.writestr(name, data)
    filename = orthogonal[0].removesuffix("_prostopadle.dxf") + "_oba.zip"
    response = FileResponse(io.BytesIO(buffer.getvalue()), as_attachment=True, filename=filename, content_type="application/zip")
    response["Cache-Control"] = "no-store"
    return response


@require_GET
@password_required
def download_dxf(request, token, name):
    owned(request, token)
    data = store.read_output(token, name)
    if data is None:
        raise Http404
    response = FileResponse(io.BytesIO(data), as_attachment=True, filename=name, content_type="application/dxf")
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def healthz(request):
    return HttpResponse("ok", content_type="text/plain")
