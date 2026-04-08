import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Anime


class MainSeasonRankingTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(username="tester", password="pass12345")
		self.client.login(username="tester", password="pass12345")

		Anime.objects.create(
			title="作品A 第1期",
			year=2020,
			season="春",
			score=Decimal("90.0"),
			is_main=True,
		)
		Anime.objects.create(
			title="作品A 第2期",
			year=2021,
			season="春",
			score=Decimal("88.0"),
			is_main=False,
		)

	def test_anime_list_default_main_mode_only_includes_main(self):
		response = self.client.get(reverse("anime_list"))
		self.assertEqual(response.status_code, 200)
		ranked = list(response.context["ranked_anime"])
		self.assertEqual(len(ranked), 1)
		self.assertTrue(ranked[0].is_main)

	def test_anime_list_ignores_ranked_mode_param_when_no_filter(self):
		response = self.client.get(reverse("anime_list"), {"ranked_mode": "season"})
		self.assertEqual(response.status_code, 200)
		ranked = list(response.context["ranked_anime"])
		self.assertEqual(len(ranked), 1)
		self.assertTrue(ranked[0].is_main)

	def test_filter_keeps_all_scored_even_when_main_is_requested(self):
		response = self.client.get(
			reverse("anime_list"),
			{"year": "2021", "ranked_mode": "main"},
		)
		self.assertEqual(response.status_code, 200)
		ranked = list(response.context["ranked_anime"])
		self.assertEqual(len(ranked), 1)
		self.assertEqual(ranked[0].title, "作品A 第2期")
		self.assertFalse(ranked[0].is_main)


class InlineMainFlagTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(username="tester2", password="pass12345")
		self.client.login(username="tester2", password="pass12345")

	def test_inline_create_accepts_is_main(self):
		response = self.client.post(
			reverse("anime_inline_create"),
			data=json.dumps(
				{
					"title": "新作 第1期",
					"year": 2026,
					"season": "春",
					"score": "80.0",
					"is_main": True,
				}
			),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["anime"]["is_main"])

	def test_inline_update_can_toggle_is_main_only(self):
		anime = Anime.objects.create(
			title="編集対象",
			year=2024,
			season="冬",
			score=Decimal("70.0"),
			is_main=False,
		)
		response = self.client.post(
			reverse("anime_inline_update", kwargs={"anime_id": anime.id}),
			data=json.dumps({"is_main": True}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		anime.refresh_from_db()
		self.assertTrue(anime.is_main)


class ExternalSearchTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(username="tester3", password="pass12345")
		self.client.login(username="tester3", password="pass12345")

	@patch("anime.views.urlrequest.urlopen")
	def test_external_search_without_year_allows_query_hit(self, mock_urlopen):
		payload = {
			"data": [
				{
					"mal_id": 1,
					"title_japanese": "テスト作品",
					"images": {"jpg": {"image_url": "https://example.com/a.jpg"}},
					"year": 2020,
					"season": "spring",
				}
			],
			"pagination": {"has_next_page": False},
		}

		mock_response = mock_urlopen.return_value.__enter__.return_value
		mock_response.read.return_value = json.dumps(payload).encode("utf-8")

		response = self.client.get(reverse("anime_external_search"), {"q": "テスト"})
		self.assertEqual(response.status_code, 200)
		body = response.json()
		self.assertTrue(body["ok"])
		self.assertEqual(len(body["items"]), 1)
		self.assertEqual(body["items"][0]["title"], "テスト作品")
		self.assertEqual(body["items"][0]["year"], 2020)


class ReorderTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(username="tester4", password="pass12345")
		self.client.login(username="tester4", password="pass12345")

	def test_reorder_response_keeps_is_main(self):
		moved = Anime.objects.create(
			title="移動対象",
			year=2026,
			season="春",
			score=Decimal("80.0"),
			is_main=True,
		)
		next_item = Anime.objects.create(
			title="次の作品",
			year=2026,
			season="春",
			score=Decimal("79.0"),
			is_main=False,
		)

		response = self.client.post(
			reverse("anime_reorder", kwargs={"anime_id": moved.id}),
			data=json.dumps({"prev_id": None, "next_id": next_item.id, "target_rank": "A"}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["anime"]["is_main"])


class RankThresholdTests(TestCase):
	def test_rank_is_ss_when_score_is_95_or_higher(self):
		anime = Anime(title="SS境界", year=2026, season="春", score=Decimal("95.0"))
		self.assertEqual(anime.rank, "SS")

	def test_rank_is_s_when_score_is_94_9(self):
		anime = Anime(title="S境界", year=2026, season="春", score=Decimal("94.9"))
		self.assertEqual(anime.rank, "S")
