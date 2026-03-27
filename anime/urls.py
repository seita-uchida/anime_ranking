from django.urls import path

from . import views

urlpatterns = [
    path("", views.anime_list, name="anime_list"),
    path("api/anime/list-chunk/", views.anime_list_chunk, name="anime_list_chunk"),
    path("api/anime/inline-create/", views.anime_inline_create, name="anime_inline_create"),
    path("api/anime/<int:anime_id>/inline-update/", views.anime_inline_update, name="anime_inline_update"),
    path("api/anime/<int:anime_id>/reorder/", views.anime_reorder, name="anime_reorder"),
    path("api/anime/<int:anime_id>/delete/", views.anime_delete, name="anime_delete"),
]
