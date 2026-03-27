import json
from decimal import Decimal, InvalidOperation
from datetime import datetime
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Anime


LIST_PAGE_SIZE = 24
SCORE_STEP = Decimal("0.1")
RANK_BOUNDS = {
	"S": (Decimal("90.0"), Decimal("100.0")),
	"A": (Decimal("80.0"), Decimal("89.9")),
	"B": (Decimal("70.0"), Decimal("79.9")),
	"C": (Decimal("60.0"), Decimal("69.9")),
	"F": (Decimal("0.0"), Decimal("59.9")),
}
SEASON_EN_TO_JA = {
	"spring": "春",
	"summer": "夏",
	"fall": "秋",
	"autumn": "秋",
	"winter": "冬",
}


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
		"year": anime.year,
		"season": anime.season,
		"score": str(anime.score) if anime.score is not None else None,
		"rank": anime.rank,
	}


def _current_year_and_season():
	# Use local timezone date so defaults match user-facing current season.
	today = timezone.localdate() if timezone.is_aware(timezone.now()) else datetime.now().date()
	month = today.month
	if 3 <= month <= 5:
		season = "春"
	elif 6 <= month <= 8:
		season = "夏"
	elif 9 <= month <= 11:
		season = "秋"
	else:
		season = "冬"
	return today.year, season


def _season_from_month(month):
	if 3 <= month <= 5:
		return "春"
	if 6 <= month <= 8:
		return "夏"
	if 9 <= month <= 11:
		return "秋"
	return "冬"


def _extract_year_season_from_jikan(item, fallback_year, fallback_season):
	year = item.get("year")
	season = SEASON_EN_TO_JA.get(str(item.get("season", "")).lower(), "")

	aired_info = item.get("aired") or {}
	aired_from = aired_info.get("from")
	if aired_from:
		try:
			parsed = datetime.fromisoformat(str(aired_from).replace("Z", "+00:00"))
			if year is None:
				year = parsed.year
			if not season:
				season = _season_from_month(parsed.month)
		except ValueError:
			pass

	if year is None:
		year = fallback_year
	if not season:
		season = fallback_season

	return int(year), season


@login_required
def anime_list(request):
	base_queryset, selected_year, selected_season = _get_filtered_queryset(request)
	current_year, current_season = _current_year_and_season()

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
			"current_year": current_year,
			"current_season": current_season,
			"default_score": "80.0",
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
@require_GET
def anime_external_search(request):
	query = str(request.GET.get("q", "")).strip()
	if len(query) < 2:
		return JsonResponse({"ok": False, "error": "検索キーワードは2文字以上で入力してください。"}, status=400)

	current_year, current_season = _current_year_and_season()
	params = urlparse.urlencode(
		{
			"q": query,
			"limit": 12,
			"sfw": "true",
			"order_by": "popularity",
			"sort": "asc",
		}
	)
	url = f"https://api.jikan.moe/v4/anime?{params}"
	request_obj = urlrequest.Request(url, headers={"User-Agent": "anime-ranking/1.0"})

	try:
		with urlrequest.urlopen(request_obj, timeout=8) as response:
			payload = json.loads(response.read().decode("utf-8"))
	except (urlerror.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
		return JsonResponse({"ok": False, "error": "外部API検索に失敗しました。しばらくして再試行してください。"}, status=502)

	items = []
	for item in payload.get("data", []):
		title = ""
		for raw_title in (item.get("title_japanese"), item.get("title"), item.get("title_english")):
			candidate = str(raw_title or "").strip()
			if candidate:
				title = candidate
				break
		if not title:
			continue

		image_url = ""
		images = item.get("images") or {}
		jpg_image = images.get("jpg") or {}
		if jpg_image.get("image_url"):
			image_url = str(jpg_image.get("image_url"))

		year, season = _extract_year_season_from_jikan(item, current_year, current_season)
		items.append(
			{
				"external_id": item.get("mal_id"),
				"title": title,
				"image_url": image_url,
				"year": year,
				"season": season,
			}
		)

	return JsonResponse({"ok": True, "items": items})


@login_required
@require_POST
def anime_external_add(request):
	try:
		payload = json.loads(request.body.decode("utf-8"))
	except (json.JSONDecodeError, UnicodeDecodeError):
		return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

	title = str(payload.get("title", "")).strip()
	image_url = str(payload.get("image_url", "")).strip()
	season = str(payload.get("season", "")).strip()

	if not title:
		return JsonResponse({"ok": False, "error": "タイトルは必須です。"}, status=400)
	if len(title) > 255:
		return JsonResponse({"ok": False, "error": "タイトルが長すぎます。"}, status=400)

	try:
		year = int(payload.get("year"))
	except (TypeError, ValueError):
		return JsonResponse({"ok": False, "error": "年度は数値で入力してください。"}, status=400)

	valid_seasons = {choice[0] for choice in Anime.SEASON_CHOICES}
	if season not in valid_seasons:
		return JsonResponse({"ok": False, "error": "シーズンが不正です。"}, status=400)

	if Anime.objects.filter(title=title, year=year, season=season).exists():
		return JsonResponse({"ok": False, "error": "同じタイトル・年度・シーズンの作品が既に存在します。"}, status=409)

	anime = Anime.objects.create(
		title=title,
		image_url=image_url,
		year=year,
		season=season,
		score=None,
	)

	return JsonResponse({"ok": True, "anime": _serialize_anime(anime)})


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
def anime_inline_create(request):
	try:
		payload = json.loads(request.body.decode("utf-8"))
	except (json.JSONDecodeError, UnicodeDecodeError):
		return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

	title = str(payload.get("title", "")).strip()
	image_url = str(payload.get("image_url", "")).strip()
	year_raw = payload.get("year")
	season = str(payload.get("season", "")).strip()
	score_raw = payload.get("score")

	if not title:
		return JsonResponse({"ok": False, "error": "タイトルは必須です。"}, status=400)
	if len(title) > 255:
		return JsonResponse({"ok": False, "error": "タイトルが長すぎます。"}, status=400)

	try:
		year = int(year_raw)
	except (TypeError, ValueError):
		return JsonResponse({"ok": False, "error": "年度は数値で入力してください。"}, status=400)

	valid_seasons = {choice[0] for choice in Anime.SEASON_CHOICES}
	if season not in valid_seasons:
		return JsonResponse({"ok": False, "error": "シーズンが不正です。"}, status=400)

	parsed_score = None
	if score_raw not in (None, ""):
		try:
			parsed_score = Decimal(str(score_raw))
		except (InvalidOperation, ValueError):
			return JsonResponse({"ok": False, "error": "点数は数値で入力してください。"}, status=400)

		if parsed_score < Decimal("0.0") or parsed_score > Decimal("100.0"):
			return JsonResponse({"ok": False, "error": "点数は0.0〜100.0で入力してください。"}, status=400)
		if parsed_score.as_tuple().exponent < -1:
			return JsonResponse({"ok": False, "error": "点数は0.1刻みで入力してください。"}, status=400)
		parsed_score = parsed_score.quantize(Decimal("0.1"))

	anime = Anime.objects.create(
		title=title,
		image_url=image_url,
		year=year,
		season=season,
		score=parsed_score,
	)

	return JsonResponse({"ok": True, "anime": _serialize_anime(anime)})


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
	target_rank = payload.get("target_rank")
	if target_rank is not None:
		target_rank = str(target_rank).strip().upper()
		if target_rank not in RANK_BOUNDS:
			return JsonResponse({"ok": False, "error": "target_rank が不正です。"}, status=400)

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
		if target_rank:
			lower, upper = RANK_BOUNDS[target_rank]
			new_score = (lower + upper) / Decimal("2")
		else:
			return JsonResponse({"ok": False, "error": "並び替え先を特定できません。"}, status=400)

	if target_rank:
		lower, upper = RANK_BOUNDS[target_rank]
		if new_score < lower:
			new_score = lower
		if new_score > upper:
			new_score = upper

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
