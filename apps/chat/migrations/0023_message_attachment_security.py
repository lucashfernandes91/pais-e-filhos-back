from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0022_event_history_and_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='attachment_size',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='message',
            name='attachment_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pendente'),
                    ('approved', 'Aprovado'),
                    ('quarantined', 'Em quarentena'),
                ],
                default='approved',
                max_length=20,
            ),
        ),
    ]
