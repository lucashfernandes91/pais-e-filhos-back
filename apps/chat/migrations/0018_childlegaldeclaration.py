from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('chat', '0017_legalacceptance'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChildLegalDeclaration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('declaration_version', models.CharField(max_length=20)),
                ('declared_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.CharField(choices=[('android', 'Android'), ('web', 'Web'), ('manual', 'Manual')], default='android', max_length=20)),
                ('child', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='legal_declaration', to='chat.child')),
                ('declared_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='child_legal_declarations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-declared_at'],
            },
        ),
    ]
