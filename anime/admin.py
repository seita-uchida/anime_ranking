from django.contrib import admin

from .models import Season, Series


class SeasonInline(admin.TabularInline):
	model = Season
	extra = 0
	fields = ("season_title", "year", "season_name", "score", "is_primary")


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
	list_display = ("title", "created_at")
	search_fields = ("title",)
	inlines = [SeasonInline]


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
	list_display = ("series", "season_title", "score", "rank", "year", "season_name", "is_primary")
	list_filter = ("season_name", "year", "is_primary")
	search_fields = ("series__title", "season_title")
	ordering = ("-score", "-year", "season_name", "series__title")
