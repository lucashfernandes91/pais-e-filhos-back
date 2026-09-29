from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_custody_holder(apps, schema_editor):
    Child = apps.get_model('chat', 'Child')
    for child in Child.objects.filter(has_custody=True, custody_holder__isnull=True).iterator():
        child.custody_holder_id = child.created_by_id
        child.save(update_fields=['custody_holder'])


def clear_custody_holder(apps, schema_editor):
    Child = apps.get_model('chat', 'Child')
    Child.objects.update(custody_holder=None)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('chat', '0018_childlegaldeclaration'),
    ]

    operations = [
        migrations.AddField(
            model_name='child',
            name='custody_holder',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='children_under_custody',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_custody_holder, clear_custody_holder),
    ]
