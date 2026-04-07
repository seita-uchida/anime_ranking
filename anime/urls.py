from django.urls import path

from . import views

urlpatterns = [
    path("", views.anime_list, name="anime_list"),
    path("series/<int:series_id>/", views.series_detail, name="series_detail"),
    path("api/series/list-chunk/", views.series_list_chunk, name="series_list_chunk"),
    path("api/series/<int:series_id>/inline-update/", views.series_inline_update, name="series_inline_update"),
    path("api/series/<int:series_id>/inline-score-update/", views.series_inline_score_update, name="series_inline_score_update"),
    path("api/series/<int:series_id>/reorder/", views.series_reorder, name="series_reorder"),
    path("api/season/<int:season_id>/inline-update/", views.season_inline_update, name="season_inline_update"),
    path("api/season/external-search/", views.season_external_search, name="season_external_search"),
    path("api/season/external-add/", views.season_external_add, name="season_external_add"),
    path("export/csv/", views.export_csv, name="export_csv"),
]
