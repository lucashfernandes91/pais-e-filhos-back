from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0021_auth_user_email_unique'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='event',
            name='version',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name='EventChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id_snapshot', models.PositiveIntegerField()),
                ('action', models.CharField(choices=[('CREATED', 'Criado'), ('UPDATED', 'Editado'), ('DELETED', 'Excluído')], max_length=10)),
                ('event_title', models.CharField(max_length=255)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('snapshot', models.JSONField(default=dict)),
                ('version', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='event_changes', to=settings.AUTH_USER_MODEL)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_changes', to='chat.conversation')),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='changes', to='chat.event')),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
    ]
