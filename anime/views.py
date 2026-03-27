from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Anime


@login_required
def anime_list(request):
	selected_year = request.GET.get("year", "")
	selected_season = request.GET.get("season", "")

	valid_seasons = {choice[0] for choice in Anime.SEASON_CHOICES}
	if selected_season and selected_season not in valid_seasons:
		selected_season = ""

	base_queryset = Anime.objects.all()
	if selected_year:
		try:
			base_queryset = base_queryset.filter(year=int(selected_year))
		except ValueError:
			selected_year = ""
	if selected_season:
		base_queryset = base_queryset.filter(season=selected_season)

	ranked_anime = base_queryset.filter(score__isnull=False).order_by(
		"-score", "-year", "season", "title"
	)
	unscored_anime = base_queryset.filter(score__isnull=True).order_by(
		"-year", "season", "title"
	)
	available_years = Anime.objects.values_list("year", flat=True).distinct().order_by("-year")

	return render(
		request,
		"anime/anime_list.html",
		{
			"ranked_anime": ranked_anime,
			"unscored_anime": unscored_anime,
			"available_years": available_years,
			"season_choices": Anime.SEASON_CHOICES,
			"selected_year": selected_year,
			"selected_season": selected_season,
		},
	)
