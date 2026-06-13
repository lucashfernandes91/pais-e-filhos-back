# Generated manually on 2026-05-20
# Adds cpf, rg, photo and has_custody fields to Child model.
# All fields are optional (null/blank allowed) as per requirements.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0006_message_attachment_message_attachment_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='child',
            name='cpf',
            field=models.CharField(blank=True, default='', max_length=14),
        ),
        migrations.AddField(
            model_name='child',
            name='rg',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='child',
            name='photo',
            field=models.ImageField(blank=True, null=True, upload_to='children_photos/'),
        ),
        migrations.AddField(
            model_name='child',
            name='has_custody',
            field=models.BooleanField(default=False),
        ),
    ]
