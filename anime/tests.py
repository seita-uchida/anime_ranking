from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Season, Series


class AnimeViewsTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="tester", password="pass12345")
		self.series = Series.objects.create(title="テスト作品")
		Season.objects.create(
			series=self.series,
			season_title="第1期",
			score=Decimal("85.0"),
			year=2024,
			season_name="春",
			is_primary=True,
		)

	def test_list_requires_login(self):
		response = self.client.get(reverse("anime_list"))
		self.assertEqual(response.status_code, 302)

	def test_list_view_after_login(self):
		self.client.login(username="tester", password="pass12345")
		response = self.client.get(reverse("anime_list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "テスト作品")

	def test_detail_view_after_login(self):
		self.client.login(username="tester", password="pass12345")
		response = self.client.get(reverse("series_detail", kwargs={"series_id": self.series.id}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "第1期")
