from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0010_event_city_localprogram'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='city',
        ),
        migrations.DeleteModel(
            name='LocalProgram',
        ),
    ]
