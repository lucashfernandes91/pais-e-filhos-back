# Generated manually — adds event_date_end to Event

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_devicetoken_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='event_date_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
