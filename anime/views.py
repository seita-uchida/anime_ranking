from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Anime


@login_required
def anime_list(request):
	ranked_anime = Anime.objects.filter(score__isnull=False).order_by(
		"-score", "-year", "season", "title"
	)
	unscored_anime = Anime.objects.filter(score__isnull=True).order_by(
		"-year", "season", "title"
	)
	return render(
		request,
		"anime/anime_list.html",
		{
			"ranked_anime": ranked_anime,
			"unscored_anime": unscored_anime,
		},
	)
