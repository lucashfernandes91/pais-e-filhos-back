from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0023_message_attachment_security'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='attachment_sha256',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
