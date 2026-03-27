from decimal import Decimal
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Anime(models.Model):
    SEASON_SPRING = "春"
    SEASON_SUMMER = "夏"
    SEASON_AUTUMN = "秋"
    SEASON_WINTER = "冬"

    SEASON_CHOICES = [
        (SEASON_SPRING, "春"),
        (SEASON_SUMMER, "夏"),
        (SEASON_AUTUMN, "秋"),
        (SEASON_WINTER, "冬"),
    ]

    title = models.CharField("アニメ名", max_length=255)
    image_url = models.URLField("画像URL", blank=True)
    score = models.DecimalField(
        "点数",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("100.0")),
        ],
        help_text="0.0〜100.0（未評価は空欄）",
    )
    year = models.IntegerField("放送年度")
    season = models.CharField("放送シーズン", max_length=1, choices=SEASON_CHOICES)
    created_at = models.DateTimeField("登録日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        ordering = ["-score", "-year", "season", "title"]
        verbose_name = "アニメ"
        verbose_name_plural = "アニメ"

    def __str__(self):
        return f"{self.title} ({self.year} {self.season})"

    @property
    def rank(self):
        if self.score is None:
            return None
        if self.score >= Decimal("90.0"):
            return "S"
        if self.score >= Decimal("80.0"):
            return "A"
        if self.score >= Decimal("70.0"):
            return "B"
        if self.score >= Decimal("60.0"):
            return "C"
        return "F"