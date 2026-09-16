from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('chat', '0016_remove_child_cpf_remove_child_rg'),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalAcceptance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('terms_version', models.CharField(max_length=20)),
                ('privacy_version', models.CharField(max_length=20)),
                ('accepted_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.CharField(choices=[('android', 'Android'), ('web', 'Web'), ('manual', 'Manual')], default='android', max_length=20)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='legal_acceptances', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-accepted_at'],
                'constraints': [
                    models.UniqueConstraint(fields=('user', 'terms_version', 'privacy_version'), name='unique_user_legal_versions'),
                ],
            },
        ),
    ]
