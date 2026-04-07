from decimal import Decimal
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Series(models.Model):
    title = models.CharField("作品名", max_length=255, unique=True)
    created_at = models.DateTimeField("登録日時", auto_now_add=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "シリーズ"
        verbose_name_plural = "シリーズ"

    def __str__(self):
        return self.title


class Season(models.Model):
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

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="seasons")
    season_title = models.CharField("シーズン名", max_length=255)
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
    season_name = models.CharField("放送シーズン", max_length=1, choices=SEASON_CHOICES)
    is_primary = models.BooleanField("代表シーズン", default=False)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        ordering = ["-year", "season_name", "season_title"]
        verbose_name = "シーズン"
        verbose_name_plural = "シーズン"
        constraints = [
            models.UniqueConstraint(
                fields=["series", "season_title"],
                name="uniq_series_season_title",
            ),
        ]

    def __str__(self):
        return f"{self.series.title} {self.season_title} ({self.year} {self.season_name})"

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