from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("anime", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="anime",
            name="is_main",
            field=models.BooleanField(default=False, verbose_name="総合ランキング掲載"),
        ),
    ]
