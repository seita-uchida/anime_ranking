import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

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


@login_required
@require_POST
def anime_inline_update(request, anime_id):
	anime = get_object_or_404(Anime, pk=anime_id)

	try:
		payload = json.loads(request.body.decode("utf-8"))
	except (json.JSONDecodeError, UnicodeDecodeError):
		return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

	title = payload.get("title")
	score = payload.get("score")

	if title is None:
		return JsonResponse({"ok": False, "error": "title は必須です。"}, status=400)

	title = str(title).strip()
	if not title:
		return JsonResponse({"ok": False, "error": "タイトルは必須です。"}, status=400)
	if len(title) > 255:
		return JsonResponse({"ok": False, "error": "タイトルが長すぎます。"}, status=400)

	parsed_score = None
	if score not in (None, ""):
		try:
			parsed_score = Decimal(str(score))
		except (InvalidOperation, ValueError):
			return JsonResponse({"ok": False, "error": "点数は数値で入力してください。"}, status=400)

		if parsed_score < Decimal("0.0") or parsed_score > Decimal("100.0"):
			return JsonResponse({"ok": False, "error": "点数は0.0〜100.0で入力してください。"}, status=400)

		# decimal_places=1 を満たすようにチェック
		if parsed_score.as_tuple().exponent < -1:
			return JsonResponse({"ok": False, "error": "点数は0.1刻みで入力してください。"}, status=400)

		parsed_score = parsed_score.quantize(Decimal("0.1"))

	anime.title = title
	anime.score = parsed_score
	anime.save()

	return JsonResponse(
		{
			"ok": True,
			"anime": {
				"id": anime.id,
				"title": anime.title,
				"score": str(anime.score) if anime.score is not None else None,
				"rank": anime.rank,
			},
		}
	)
