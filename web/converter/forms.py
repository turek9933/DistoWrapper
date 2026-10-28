import os

from django import forms
from django.conf import settings

from distocad import Options

VERSION_CHOICES = [
    ("orthogonal", "Prostopadła (kąty proste, wyprostowane pomieszczenia)"),
    ("original", "Oryginalna (kierunki i kąty ze szkicu, wszystkie linie)"),
    ("both", "Obie wersje"),
]
LAYOUT_CHOICES = [
    ("sketch", "Jak w szkicu (zachowane rozmieszczenie)"),
    ("row", "W rzędzie (oszczędza miejsce)"),
]
ALLOWED_EXTENSIONS = (".cmi", ".xml")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": ".cmi,.xml"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)]


class ConvertForm(forms.Form):
    files = MultipleFileField(label="Pliki .cmi lub .xml")
    version = forms.ChoiceField(label="Wersja rysunku", choices=VERSION_CHOICES, initial="both", widget=forms.RadioSelect)
    labels = forms.BooleanField(label="Etykiety długości ścian w wersji prostopadłej (oryginalna zawsze ma etykiety)", required=False, initial=False)
    layout = forms.ChoiceField(label="Układ pomieszczeń", choices=LAYOUT_CHOICES, initial="sketch", widget=forms.RadioSelect)
    gap_circles = forms.BooleanField(label="Okręgi przy szczelinach w wersji prostopadłej", required=False, initial=True)
    layers = forms.BooleanField(label="Warstwy i kolory zamiast warstwy 0", required=False)
    title = forms.BooleanField(label="Tytuł rysunku (tylko wersja prostopadła)", required=False, initial=True)
    name = forms.CharField(label="Nazwa rysunku (opcjonalnie, jeden plik)", max_length=120, required=False)
    free_limit = forms.FloatField(label="Ściana jest nieortogonalna od odchyłki (stopnie)", min_value=1, max_value=44, initial=25, required=False)
    gap_threshold = forms.FloatField(label="Próg szczeliny i ostrzeżenia (mm)", min_value=0, initial=15, required=False)
    spacing = forms.FloatField(label="Odstęp między pomieszczeniami w układzie rzędu (mm)", min_value=0, initial=1000, required=False)

    def clean_files(self):
        files = self.cleaned_data["files"]
        max_files = settings.DISTO_MAX_FILES
        if max_files and len(files) > max_files:
            raise forms.ValidationError(f"Najwyżej {max_files} plików naraz")
        total = 0
        for item in files:
            if not item.name.lower().endswith(ALLOWED_EXTENSIONS):
                raise forms.ValidationError(f"Niewłaściwe rozszerzenie: {os.path.basename(item.name)} (dozwolone: .cmi, .xml)")
            if settings.DISTO_MAX_FILE_BYTES and item.size > settings.DISTO_MAX_FILE_BYTES:
                raise forms.ValidationError(f"Plik {os.path.basename(item.name)} jest zbyt duży")
            total += item.size
        if settings.DISTO_MAX_TOTAL_BYTES and total > settings.DISTO_MAX_TOTAL_BYTES:
            raise forms.ValidationError("Łączny rozmiar plików jest zbyt duży")
        return files

    def clean(self):
        data = super().clean()
        if data.get("name") and len(data.get("files") or []) > 1:
            raise forms.ValidationError("Nazwę ręczną można ustawić tylko dla jednego pliku")
        return data

    def options(self):
        data = self.cleaned_data
        defaults = Options()

        def number(name, fallback):
            value = data.get(name)
            return fallback if value is None else value

        return Options(
            version=data["version"],
            labels=data["labels"],
            layout=data["layout"],
            gap_threshold=number("gap_threshold", defaults.gap_threshold),
            gap_circles=data["gap_circles"],
            layers=data["layers"],
            free_limit=number("free_limit", defaults.free_limit),
            spacing=number("spacing", defaults.spacing),
            title=data["title"],
            name=data.get("name") or None,
        )
