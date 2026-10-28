from django.urls import path

from . import views

app_name = "converter"

urlpatterns = [
    path("", views.index, name="index"),
    path("haslo/", views.login, name="login"),
    path("healthz/", views.healthz, name="healthz"),
    path("wynik/<str:token>/", views.result, name="result"),
    path("pobierz/<str:token>/oba/", views.download_both, name="download_both"),
    path("pobierz/<str:token>/<str:kind>/", views.download, name="download"),
    path("pobierz/<str:token>/dxf/<str:name>/", views.download_dxf, name="download_dxf"),
]
