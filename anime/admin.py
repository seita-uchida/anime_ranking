from django.contrib import admin

from .models import Anime


@admin.register(Anime)
class AnimeAdmin(admin.ModelAdmin):
	list_display = ("title", "score", "rank", "year", "season", "updated_at")
	list_filter = ("season", "year")
	search_fields = ("title",)
	ordering = ("-score", "-year", "season", "title")
