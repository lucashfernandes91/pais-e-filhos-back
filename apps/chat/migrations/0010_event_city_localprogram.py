from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0009_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='city',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.CreateModel(
            name='LocalProgram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('city', models.CharField(max_length=120)),
                ('venue', models.CharField(blank=True, default='', max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('start_at', models.DateTimeField()),
                ('end_at', models.DateTimeField()),
                ('source_url', models.URLField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['start_at'],
            },
        ),
    ]
