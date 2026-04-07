from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def forwards_copy_data(apps, schema_editor):
    Anime = apps.get_model("anime", "Anime")
    Series = apps.get_model("anime", "Series")
    Season = apps.get_model("anime", "Season")

    for anime in Anime.objects.all().order_by("id"):
        series, _ = Series.objects.get_or_create(title=anime.title)

        base_title = f"{anime.year}年{anime.season}"
        season_title = base_title
        suffix = 2
        while Season.objects.filter(series=series, season_title=season_title).exists():
            season_title = f"{base_title}-{suffix}"
            suffix += 1

        is_primary = not Season.objects.filter(series=series, is_primary=True).exists()
        score = anime.score
        if score is not None:
            score = Decimal(score).quantize(Decimal("0.1"))

        Season.objects.create(
            series=series,
            season_title=season_title,
            image_url=anime.image_url,
            score=score,
            year=anime.year,
            season_name=anime.season,
            is_primary=is_primary,
            updated_at=anime.updated_at,
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("anime", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Series",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, unique=True, verbose_name="作品名")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="登録日時")),
            ],
            options={
                "verbose_name": "シリーズ",
                "verbose_name_plural": "シリーズ",
                "ordering": ["title"],
            },
        ),
        migrations.CreateModel(
            name="Season",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("season_title", models.CharField(max_length=255, verbose_name="シーズン名")),
                ("image_url", models.URLField(blank=True, verbose_name="画像URL")),
                (
                    "score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        help_text="0.0〜100.0（未評価は空欄）",
                        max_digits=4,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.0")),
                            django.core.validators.MaxValueValidator(Decimal("100.0")),
                        ],
                        verbose_name="点数",
                    ),
                ),
                ("year", models.IntegerField(verbose_name="放送年度")),
                (
                    "season_name",
                    models.CharField(
                        choices=[("春", "春"), ("夏", "夏"), ("秋", "秋"), ("冬", "冬")],
                        max_length=1,
                        verbose_name="放送シーズン",
                    ),
                ),
                ("is_primary", models.BooleanField(default=False, verbose_name="代表シーズン")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新日時")),
                (
                    "series",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seasons", to="anime.series"),
                ),
            ],
            options={
                "verbose_name": "シーズン",
                "verbose_name_plural": "シーズン",
                "ordering": ["-year", "season_name", "season_title"],
            },
        ),
        migrations.AddConstraint(
            model_name="season",
            constraint=models.UniqueConstraint(fields=("series", "season_title"), name="uniq_series_season_title"),
        ),
        migrations.RunPython(forwards_copy_data, reverse_code=noop_reverse),
        migrations.DeleteModel(name="Anime"),
    ]
