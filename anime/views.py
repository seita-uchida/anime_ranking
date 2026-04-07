import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Avg, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Season, Series


LIST_PAGE_SIZE = 20
SCORE_STEP = Decimal("0.1")
SEASON_EN_TO_JA = {
    "spring": "春",
    "summer": "夏",
    "fall": "秋",
    "autumn": "秋",
    "winter": "冬",
}
SEASON_JA_TO_EN = {
    "春": "spring",
    "夏": "summer",
    "秋": "fall",
    "冬": "winter",
}


def _current_year_and_season():
    today = timezone.localdate() if timezone.is_aware(timezone.now()) else datetime.now().date()
    month = today.month
    if 3 <= month <= 5:
        return today.year, "春"
    if 6 <= month <= 8:
        return today.year, "夏"
    if 9 <= month <= 11:
        return today.year, "秋"
    return today.year, "冬"


def _season_from_month(month):
    if 3 <= month <= 5:
        return "春"
    if 6 <= month <= 8:
        return "夏"
    if 9 <= month <= 11:
        return "秋"
    return "冬"


def _rank_from_score(score):
    if score is None:
        return None
    if score >= Decimal("90.0"):
        return "S"
    if score >= Decimal("80.0"):
        return "A"
    if score >= Decimal("70.0"):
        return "B"
    if score >= Decimal("60.0"):
        return "C"
    return "F"


def _parse_score(score_raw):
    if score_raw in (None, ""):
        return None
    try:
        parsed_score = Decimal(str(score_raw))
    except (InvalidOperation, ValueError):
        raise ValueError("点数は数値で入力してください。")

    if parsed_score < Decimal("0.0") or parsed_score > Decimal("100.0"):
        raise ValueError("点数は0.0〜100.0で入力してください。")
    if parsed_score.as_tuple().exponent < -1:
        raise ValueError("点数は0.1刻みで入力してください。")
    return parsed_score.quantize(Decimal("0.1"))


def _parse_filters(request):
    score_mode = request.GET.get("score_mode", "primary")
    if score_mode not in ("primary", "average"):
        score_mode = "primary"

    selected_year = request.GET.get("year", "")
    selected_season = request.GET.get("season", "")
    q = request.GET.get("q", "").strip()
    zone = request.GET.get("zone", "all")

    valid_seasons = {choice[0] for choice in Season.SEASON_CHOICES}
    if selected_season and selected_season not in valid_seasons:
        selected_season = ""
    if zone not in ("all", "ranked", "unscored"):
        zone = "all"

    return {
        "score_mode": score_mode,
        "selected_year": selected_year,
        "selected_season": selected_season,
        "q": q,
        "zone": zone,
    }


def _base_series_queryset(filters):
    series_qs = Series.objects.all()
    season_filter = Q()

    if filters["selected_year"]:
        try:
            year_int = int(filters["selected_year"])
        except ValueError:
            year_int = None
        if year_int is not None:
            season_filter &= Q(seasons__year=year_int)
        else:
            filters["selected_year"] = ""

    if filters["selected_season"]:
        season_filter &= Q(seasons__season_name=filters["selected_season"])

    if filters["q"]:
        season_filter &= (
            Q(title__icontains=filters["q"])
            | Q(seasons__season_title__icontains=filters["q"])
        )

    return series_qs.filter(season_filter).distinct()


def _representative_score(series, mode):
    if mode == "average":
        scores = [s.score for s in series.seasons.all() if s.score is not None]
        if not scores:
            return None
        avg = sum(scores) / Decimal(len(scores))
        return avg.quantize(Decimal("0.1"))

    primary = next((s for s in series.seasons.all() if s.is_primary), None)
    if primary:
        return primary.score

    first = (
        sorted(series.seasons.all(), key=lambda x: (x.year, x.id))[0]
        if series.seasons.all()
        else None
    )
    return first.score if first else None


def _series_card(series, mode):
    seasons = list(series.seasons.all())
    primary = next((s for s in seasons if s.is_primary), None)
    earliest = sorted(seasons, key=lambda x: (x.year, x.id))[0] if seasons else None
    representative = _representative_score(series, mode)

    season_ref = primary or earliest
    image_url = ""
    if season_ref and season_ref.image_url:
        image_url = season_ref.image_url

    return {
        "id": series.id,
        "title": series.title,
        "season_count": len(seasons),
        "score": str(representative) if representative is not None else None,
        "rank": _rank_from_score(representative),
        "image_url": image_url,
        "primary_season_id": primary.id if primary else None,
    }


def _list_payload(filters, page):
    qs = _base_series_queryset(filters).prefetch_related("seasons")

    rows = []
    for series in qs:
        card = _series_card(series, filters["score_mode"])
        if filters["zone"] == "ranked" and card["score"] is None:
            continue
        if filters["zone"] == "unscored" and card["score"] is not None:
            continue
        rows.append(card)

    rows.sort(
        key=lambda item: (
            item["score"] is None,
            Decimal(item["score"]) if item["score"] is not None else Decimal("-1"),
            item["title"],
        ),
        reverse=False,
    )
    rows.sort(key=lambda item: Decimal(item["score"]) if item["score"] is not None else Decimal("-1"), reverse=True)

    paginator = Paginator(rows, LIST_PAGE_SIZE)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        return [], False, None

    return list(page_obj.object_list), page_obj.has_next(), (page_obj.next_page_number() if page_obj.has_next() else None)


@login_required
def anime_list(request):
    filters = _parse_filters(request)
    items, has_next, next_page = _list_payload(filters, 1)
    current_year, current_season = _current_year_and_season()

    available_years = (
        Season.objects.values_list("year", flat=True).distinct().order_by("-year")
    )

    return render(
        request,
        "anime/anime_list.html",
        {
            "series_cards": items,
            "has_next": has_next,
            "next_page": next_page,
            "score_mode": filters["score_mode"],
            "selected_year": filters["selected_year"],
            "selected_season": filters["selected_season"],
            "selected_zone": filters["zone"],
            "query": filters["q"],
            "available_years": available_years,
            "season_choices": Season.SEASON_CHOICES,
            "current_year": current_year,
            "current_season": current_season,
        },
    )


@login_required
@require_GET
def series_list_chunk(request):
    filters = _parse_filters(request)
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        return JsonResponse({"ok": False, "error": "page が不正です。"}, status=400)

    if page < 1:
        return JsonResponse({"ok": False, "error": "page は1以上です。"}, status=400)

    items, has_next, next_page = _list_payload(filters, page)
    return JsonResponse(
        {
            "ok": True,
            "items": items,
            "has_next": has_next,
            "next_page": next_page,
        }
    )


@login_required
def series_detail(request, series_id):
    series = get_object_or_404(Series.objects.prefetch_related("seasons"), pk=series_id)
    seasons = list(series.seasons.all().order_by("year", "season_name", "id"))

    average_score = None
    scored = [s.score for s in seasons if s.score is not None]
    if scored:
        average_score = (sum(scored) / Decimal(len(scored))).quantize(Decimal("0.1"))

    return render(
        request,
        "anime/series_detail.html",
        {
            "series": series,
            "seasons": seasons,
            "average_score": average_score,
        },
    )


@login_required
@require_POST
def season_inline_update(request, season_id):
    season = get_object_or_404(Season, pk=season_id)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

    season_title = payload.get("season_title")
    if season_title is not None:
        season_title = str(season_title).strip()
        if not season_title:
            return JsonResponse({"ok": False, "error": "シーズン名は必須です。"}, status=400)
        season.season_title = season_title

    if "score" in payload:
        try:
            season.score = _parse_score(payload.get("score"))
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    if "is_primary" in payload:
        flag = bool(payload.get("is_primary"))
        if flag:
            Season.objects.filter(series=season.series, is_primary=True).exclude(pk=season.pk).update(is_primary=False)
        season.is_primary = flag

    season.save()
    return JsonResponse(
        {
            "ok": True,
            "season": {
                "id": season.id,
                "season_title": season.season_title,
                "score": str(season.score) if season.score is not None else None,
                "rank": season.rank,
                "is_primary": season.is_primary,
            },
        }
    )


@login_required
@require_POST
def series_inline_update(request, series_id):
    series = get_object_or_404(Series, pk=series_id)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

    title = str(payload.get("title", "")).strip()
    if not title:
        return JsonResponse({"ok": False, "error": "作品名は必須です。"}, status=400)
    if len(title) > 255:
        return JsonResponse({"ok": False, "error": "作品名が長すぎます。"}, status=400)

    if Series.objects.exclude(pk=series.pk).filter(title=title).exists():
        return JsonResponse({"ok": False, "error": "同名シリーズが既に存在します。"}, status=409)

    series.title = title
    series.save(update_fields=["title"])
    return JsonResponse({"ok": True, "series": {"id": series.id, "title": series.title}})


@login_required
@require_POST
def series_inline_score_update(request, series_id):
    series = get_object_or_404(Series.objects.prefetch_related("seasons"), pk=series_id)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

    if "score" not in payload:
        return JsonResponse({"ok": False, "error": "score は必須です。"}, status=400)

    try:
        parsed_score = _parse_score(payload.get("score"))
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    primary = series.seasons.filter(is_primary=True).first()
    if primary is None:
        primary = series.seasons.order_by("year", "id").first()
        if primary is None:
            return JsonResponse({"ok": False, "error": "このシリーズにシーズンがありません。"}, status=400)
        Season.objects.filter(series=series, is_primary=True).exclude(pk=primary.pk).update(is_primary=False)
        primary.is_primary = True

    primary.score = parsed_score
    primary.save()

    return JsonResponse(
        {
            "ok": True,
            "season": {
                "id": primary.id,
                "score": str(primary.score) if primary.score is not None else None,
                "rank": primary.rank,
            },
        }
    )


@login_required
@require_POST
def series_reorder(request, series_id):
    moved_series = get_object_or_404(Series.objects.prefetch_related("seasons"), pk=series_id)
    moved_primary = moved_series.seasons.filter(is_primary=True).first()
    if moved_primary is None:
        return JsonResponse({"ok": False, "error": "代表シーズンが設定されていません。"}, status=400)
    if moved_primary.score is None:
        return JsonResponse({"ok": False, "error": "未評価シリーズは並び替えできません。"}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

    prev_id = payload.get("prev_id")
    next_id = payload.get("next_id")

    def _primary_score(series_pk):
        if series_pk is None:
            return None
        try:
            value = int(series_pk)
        except (TypeError, ValueError):
            return "invalid"
        neighbor = Series.objects.filter(pk=value).first()
        if not neighbor:
            return "invalid"
        ps = neighbor.seasons.filter(is_primary=True).first()
        return ps.score if ps else None

    prev_score = _primary_score(prev_id)
    next_score = _primary_score(next_id)

    if prev_score == "invalid" or next_score == "invalid":
        return JsonResponse({"ok": False, "error": "並び替え対象が不正です。"}, status=400)

    if prev_score is not None and next_score is not None:
        new_score = (prev_score + next_score) / Decimal("2")
    elif prev_score is not None:
        new_score = prev_score - SCORE_STEP
    elif next_score is not None:
        new_score = next_score + SCORE_STEP
    else:
        return JsonResponse({"ok": False, "error": "並び替え先を特定できません。"}, status=400)

    if new_score < Decimal("0.0"):
        new_score = Decimal("0.0")
    if new_score > Decimal("100.0"):
        new_score = Decimal("100.0")

    moved_primary.score = new_score.quantize(SCORE_STEP)
    moved_primary.save(update_fields=["score", "updated_at"])

    return JsonResponse(
        {
            "ok": True,
            "primary_season_id": moved_primary.id,
            "score": str(moved_primary.score),
            "rank": moved_primary.rank,
        }
    )


@login_required
@require_GET
def season_external_search(request):
    query = str(request.GET.get("q", "")).strip()
    selected_season = str(request.GET.get("season", "")).strip()
    selected_year_raw = str(request.GET.get("year", "")).strip()

    if query and len(query) < 2:
        return JsonResponse({"ok": False, "error": "検索キーワードは2文字以上で入力してください。"}, status=400)

    valid_seasons = {choice[0] for choice in Season.SEASON_CHOICES}
    if selected_season and selected_season not in valid_seasons:
        return JsonResponse({"ok": False, "error": "シーズン指定が不正です。"}, status=400)

    current_year, current_season = _current_year_and_season()
    selected_year = current_year
    if selected_year_raw:
        try:
            selected_year = int(selected_year_raw)
        except ValueError:
            return JsonResponse({"ok": False, "error": "年度指定が不正です。"}, status=400)

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        return JsonResponse({"ok": False, "error": "page が不正です。"}, status=400)

    if page < 1:
        return JsonResponse({"ok": False, "error": "page は1以上です。"}, status=400)

    if query:
        params = urlparse.urlencode({"q": query, "limit": 8, "page": page, "sfw": "true"})
        url = f"https://api.jikan.moe/v4/anime?{params}"
    else:
        if selected_season:
            season_en = SEASON_JA_TO_EN[selected_season]
            params = urlparse.urlencode({"limit": 8, "page": page, "sfw": "true"})
            url = f"https://api.jikan.moe/v4/seasons/{selected_year}/{season_en}?{params}"
        else:
            params = urlparse.urlencode({"limit": 8, "page": page, "sfw": "true"})
            url = f"https://api.jikan.moe/v4/seasons/{selected_year}?{params}"

    request_obj = urlrequest.Request(url, headers={"User-Agent": "anime-ranking/2.0"})
    try:
        with urlrequest.urlopen(request_obj, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "外部API検索に失敗しました。"}, status=502)

    results = []
    for item in payload.get("data", []):
        title = ""
        for raw in (item.get("title_japanese"), item.get("title"), item.get("title_english")):
            candidate = str(raw or "").strip()
            if candidate:
                title = candidate
                break
        if not title:
            continue

        image_url = ""
        images = item.get("images") or {}
        jpg = images.get("jpg") or {}
        if jpg.get("image_url"):
            image_url = str(jpg.get("image_url"))

        year = item.get("year")
        season_name = SEASON_EN_TO_JA.get(str(item.get("season", "")).lower(), "")
        aired = (item.get("aired") or {}).get("from")
        if aired:
            try:
                parsed = datetime.fromisoformat(str(aired).replace("Z", "+00:00"))
                if year is None:
                    year = parsed.year
                if not season_name:
                    season_name = _season_from_month(parsed.month)
            except ValueError:
                pass

        if year is None:
            year = selected_year
        if not season_name:
            season_name = current_season

        results.append(
            {
                "title": title,
                "season_title": str(item.get("title") or "第1期"),
                "image_url": image_url,
                "year": int(year),
                "season_name": season_name,
            }
        )

    pagination = payload.get("pagination") or {}
    has_next = bool(pagination.get("has_next_page"))
    return JsonResponse({"ok": True, "items": results, "has_next": has_next, "next_page": (page + 1 if has_next else None)})


@login_required
@require_POST
def season_external_add(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "JSON形式が不正です。"}, status=400)

    title = str(payload.get("title", "")).strip()
    season_title = str(payload.get("season_title", "")).strip() or "第1期"
    image_url = str(payload.get("image_url", "")).strip()
    season_name = str(payload.get("season_name", "")).strip()

    if not title:
        return JsonResponse({"ok": False, "error": "作品名は必須です。"}, status=400)

    valid_seasons = {choice[0] for choice in Season.SEASON_CHOICES}
    if season_name not in valid_seasons:
        return JsonResponse({"ok": False, "error": "シーズンが不正です。"}, status=400)

    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "年度は数値で入力してください。"}, status=400)

    try:
        score = _parse_score(payload.get("score"))
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    series, _ = Series.objects.get_or_create(title=title)

    if Season.objects.filter(series=series, season_title=season_title).exists():
        return JsonResponse({"ok": False, "error": "同名シーズンが既に存在します。"}, status=409)

    is_primary = not series.seasons.filter(is_primary=True).exists()
    season = Season.objects.create(
        series=series,
        season_title=season_title,
        image_url=image_url,
        score=score,
        year=year,
        season_name=season_name,
        is_primary=is_primary,
    )

    return JsonResponse({"ok": True, "series_id": series.id, "season_id": season.id})


@login_required
@require_GET
def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="anime_backup.csv"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(
        [
            "series_title",
            "season_title",
            "score",
            "rank",
            "year",
            "season_name",
            "is_primary",
            "image_url",
        ]
    )

    rows = Season.objects.select_related("series").order_by("series__title", "year", "season_name")
    for season in rows:
        writer.writerow(
            [
                season.series.title,
                season.season_title,
                season.score if season.score is not None else "",
                season.rank or "",
                season.year,
                season.season_name,
                "1" if season.is_primary else "0",
                season.image_url,
            ]
        )

    return response
