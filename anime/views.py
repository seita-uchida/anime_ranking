import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import Anime


LIST_PAGE_SIZE = 24
SCORE_STEP = Decimal("0.1")


def _get_filtered_queryset(request):
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

	return base_queryset, selected_year, selected_season


def _serialize_anime(anime):
	return {
		"id": anime.id,
		"title": anime.title,
		"image_url": anime.image_url,
		"score": str(anime.score) if anime.score is not None else None,
		"rank": anime.rank,
	}


@login_required
def anime_list(request):
	base_queryset, selected_year, selected_season = _get_filtered_queryset(request)

	ranked_qs = base_queryset.filter(score__isnull=False).order_by(
		"-score", "-year", "season", "title"
	)
	unscored_qs = base_queryset.filter(score__isnull=True).order_by(
		"-year", "season", "title"
	)

	ranked_page = Paginator(ranked_qs, LIST_PAGE_SIZE).get_page(1)
	unscored_page = Paginator(unscored_qs, LIST_PAGE_SIZE).get_page(1)
	available_years = Anime.objects.values_list("year", flat=True).distinct().order_by("-year")

	return render(
		request,
		"anime/anime_list.html",
		{
			"ranked_anime": ranked_page.object_list,
			"unscored_anime": unscored_page.object_list,
			"ranked_has_next": ranked_page.has_next(),
			"unscored_has_next": unscored_page.has_next(),
			"ranked_next_page": ranked_page.next_page_number() if ranked_page.has_next() else None,
			"unscored_next_page": unscored_page.next_page_number() if unscored_page.has_next() else None,
			"available_years": available_years,
			"season_choices": Anime.SEASON_CHOICES,
			"selected_year": selected_year,
			"selected_season": selected_season,
		},
	)


@login_required
@require_GET
def anime_list_chunk(request):
	zone = request.GET.get("zone", "ranked")
	if zone not in ("ranked", "unscored"):
		return JsonResponse({"ok": False, "error": "zone が不正です。"}, status=400)

	page_raw = request.GET.get("page", "1")
	try:
		page_num = int(page_raw)
	except ValueError:
		return JsonResponse({"ok": False, "error": "page が不正です。"}, status=400)

	if page_num < 1:
		return JsonResponse({"ok": False, "error": "page は1以上です。"}, status=400)

	base_queryset, _, _ = _get_filtered_queryset(request)
	if zone == "ranked":
		queryset = base_queryset.filter(score__isnull=False).order_by("-score", "-year", "season", "title")
	else:
		queryset = base_queryset.filter(score__isnull=True).order_by("-year", "season", "title")

	paginator = Paginator(queryset, LIST_PAGE_SIZE)
	try:
		page_obj = paginator.page(page_num)
	except EmptyPage:
		return JsonResponse({"ok": True, "items": [], "has_next": False, "next_page": None})

	return JsonResponse(
		{
			"ok": True,
			"items": [_serialize_anime(anime) for anime in page_obj.object_list],
			"has_next": page_obj.has_next(),
			"next_page": page_obj.next_page_number() if page_obj.has_next() else None,
		}
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


@login_required
@require_POST
def anime_reorder(request, anime_id):
	moved = get_object_or_404(Anime, pk=anime_id)
	if moved.score is None:
		return JsonResponse({"ok": False, "error": "未評価作品は並び替えできません。"}, status=400)

	try:
		payload = json.loads(request.body.decode("utf-8"))
	except (json.JSONDecodeError, UnicodeDecodeError):
		return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

	prev_id = payload.get("prev_id")
	next_id = payload.get("next_id")

	prev_anime = None
	next_anime = None

	if prev_id is not None:
		try:
			prev_anime = Anime.objects.get(pk=int(prev_id), score__isnull=False)
		except (ValueError, Anime.DoesNotExist):
			return JsonResponse({"ok": False, "error": "前の作品が見つかりません。"}, status=400)

	if next_id is not None:
		try:
			next_anime = Anime.objects.get(pk=int(next_id), score__isnull=False)
		except (ValueError, Anime.DoesNotExist):
			return JsonResponse({"ok": False, "error": "次の作品が見つかりません。"}, status=400)

	if prev_anime and next_anime and prev_anime.score <= next_anime.score:
		return JsonResponse({"ok": False, "error": "並び替え情報が不正です。"}, status=400)

	if prev_anime and next_anime:
		new_score = (prev_anime.score + next_anime.score) / Decimal("2")
	elif prev_anime:
		new_score = prev_anime.score - SCORE_STEP
	elif next_anime:
		new_score = next_anime.score + SCORE_STEP
	else:
		return JsonResponse({"ok": False, "error": "並び替え先を特定できません。"}, status=400)

	if new_score < Decimal("0.0"):
		new_score = Decimal("0.0")
	if new_score > Decimal("100.0"):
		new_score = Decimal("100.0")

	new_score = new_score.quantize(SCORE_STEP)
	moved.score = new_score
	moved.save(update_fields=["score", "updated_at"])

	return JsonResponse(
		{
			"ok": True,
			"anime": {
				"id": moved.id,
				"score": str(moved.score),
				"rank": moved.rank,
			},
		}
	)


@login_required
@require_POST
def anime_delete(request, anime_id):
	anime = get_object_or_404(Anime, pk=anime_id)
	anime.delete()
	return JsonResponse({"ok": True, "deleted_id": anime_id})
