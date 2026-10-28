import io
import json
import tempfile
import zipfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from converter.forms import ConvertForm
from distocad.testing import make_cmi, rectangle


def upload(name, data):
    return SimpleUploadedFile(name, data, content_type="application/octet-stream")


class ConverterViewTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = override_settings(DISTO_EPHEMERAL_DIR=self.tmp.name)
        self.override.enable()
        cache.clear()
        self.client = Client()
        self.good = make_cmi([rectangle(300, 200, 3.15, 2.0)])

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def post(self, files, **extra):
        data = {
            "files": files,
            "version": "orthogonal",
            "gap_circles": "on",
            "layout": "sketch",
            "title": "on",
            "free_limit": "25",
            "gap_threshold": "15",
            "spacing": "1000",
        }
        data.update(extra)
        return self.client.post("/", data)

    def token(self, response):
        return response["Location"].rstrip("/").split("/")[-1]

    def test_index(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Konwertuj")

    def test_form_defaults(self):
        form = ConvertForm()
        self.assertFalse(form.fields["labels"].initial)
        self.assertTrue(form.fields["gap_circles"].initial)

    def test_healthz(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_single_file_direct_dxf(self):
        response = self.post([upload("mieszkanie.cmi", self.good)])
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response["Location"])
        self.assertContains(page, "Wykonano")
        self.assertNotContains(page, "Pobierz ZIP")
        self.assertNotContains(page, "Pobierz oba")
        token = self.token(response)
        self.assertEqual(self.client.get(f"/pobierz/{token}/oba/").status_code, 404)
        dxf = self.client.get(f"/pobierz/{token}/dxf/mieszkanie.dxf/")
        self.assertEqual(dxf.status_code, 200)
        self.assertIn("mieszkanie.dxf", dxf["Content-Disposition"])
        self.assertIn(b"LWPOLYLINE", b"".join(dxf.streaming_content))
        report = json.loads(b"".join(self.client.get(f"/pobierz/{token}/report/").streaming_content))
        self.assertEqual(report["summary"]["rooms"], 1)

    def test_single_file_both_versions_has_two_direct_links_and_both_zip(self):
        response = self.post([upload("mieszkanie.cmi", self.good)], version="both")
        page = self.client.get(response["Location"])
        self.assertContains(page, "mieszkanie_prostopadle.dxf")
        self.assertContains(page, "mieszkanie_oryginal.dxf")
        self.assertContains(page, "Pobierz oba")
        self.assertNotContains(page, "Pobierz ZIP")
        token = self.token(response)
        for name in ("mieszkanie_prostopadle.dxf", "mieszkanie_oryginal.dxf"):
            self.assertEqual(self.client.get(f"/pobierz/{token}/dxf/{name}/").status_code, 200)
        both = self.client.get(f"/pobierz/{token}/oba/")
        self.assertEqual(both.status_code, 200)
        self.assertEqual(both["Content-Type"], "application/zip")
        self.assertIn("mieszkanie_oba.zip", both["Content-Disposition"])
        archive = zipfile.ZipFile(io.BytesIO(b"".join(both.streaming_content)))
        self.assertEqual(
            sorted(archive.namelist()),
            ["mieszkanie_oryginal.dxf", "mieszkanie_prostopadle.dxf"],
        )

    def test_multiple_files_zip_names(self):
        response = self.post([upload("a.cmi", self.good), upload("b.cmi", self.good)], version="both")
        page = self.client.get(response["Location"])
        self.assertContains(page, "Pobierz ZIP")
        self.assertNotContains(page, "Pobierz oba")
        token = self.token(response)
        archive = zipfile.ZipFile(io.BytesIO(b"".join(self.client.get(f"/pobierz/{token}/zip/").streaming_content)))
        self.assertEqual(
            sorted(archive.namelist()),
            ["a_oryginal.dxf", "a_prostopadle.dxf", "b_oryginal.dxf", "b_prostopadle.dxf", "report.json"],
        )

    def test_other_session_cannot_download(self):
        response = self.post([upload("a.cmi", self.good)])
        token = self.token(response)
        stranger = Client()
        self.assertEqual(stranger.get(f"/pobierz/{token}/zip/").status_code, 404)
        self.assertEqual(stranger.get(f"/wynik/{token}/").status_code, 404)
        self.assertEqual(stranger.get(f"/pobierz/{token}/dxf/a.dxf/").status_code, 404)

    def test_bad_extension_rejected(self):
        response = self.post([upload("a.txt", b"x")])
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Niewłaściwe rozszerzenie", status_code=400)

    def test_garbage_file_reports_error(self):
        response = self.post([upload("a.cmi", b"nonsense")])
        page = self.client.get(response["Location"])
        self.assertContains(page, "Nie utworzono żadnego rysunku")

    def test_partial_room_is_drawn_without_retry(self):
        walls = rectangle(300, 200, 3.0, 2.0)
        walls[1] = walls[1][:4] + ("NaN",)
        response = self.post([upload("a.cmi", make_cmi([walls]))])
        page = self.client.get(response["Location"])
        self.assertContains(page, "Wykonano")
        self.assertContains(page, "Brak pomiaru")
        self.assertNotContains(page, "Narysuj mimo ostrzeżeń")

    def test_manual_name(self):
        response = self.post([upload("a.cmi", self.good)], name="Mieszkanie 1")
        page = self.client.get(response["Location"])
        self.assertContains(page, "Mieszkanie 1.dxf")

    def test_manual_name_rejected_for_multiple_files(self):
        response = self.post([upload("a.cmi", self.good), upload("b.cmi", self.good)], name="x")
        self.assertEqual(response.status_code, 400)

    @override_settings(DISTO_PASSWORD="secret")
    def test_password_required(self):
        response = self.client.get("/")
        self.assertRedirects(response, reverse("converter:login"))
        bad = self.client.post(reverse("converter:login"), {"password": "wrong"})
        self.assertContains(bad, "Nieprawidłowe hasło")
        good = self.client.post(reverse("converter:login"), {"password": "secret"})
        self.assertRedirects(good, reverse("converter:index"))
        self.assertEqual(self.client.get("/").status_code, 200)

    @override_settings(DISTO_RATE_LIMIT=1)
    def test_rate_limit(self):
        self.post([upload("a.cmi", self.good)])
        self.post([upload("a.cmi", self.good)])
        response = self.post([upload("a.cmi", self.good)])
        self.assertEqual(response.status_code, 429)

    @override_settings(DISTO_MAX_FILES=1)
    def test_too_many_files(self):
        response = self.post([upload("a.cmi", self.good), upload("b.cmi", self.good)])
        self.assertEqual(response.status_code, 400)

    @override_settings(DISTO_MAX_FILES=0, DISTO_MAX_FILE_BYTES=0, DISTO_MAX_TOTAL_BYTES=0)
    def test_zero_limits_mean_unlimited(self):
        response = self.post([upload("a.cmi", self.good), upload("b.cmi", self.good)])
        self.assertEqual(response.status_code, 302)

    def test_invalid_token_is_not_a_path(self):
        self.assertEqual(self.client.get("/pobierz/..%2Fetc/zip/").status_code, 404)
