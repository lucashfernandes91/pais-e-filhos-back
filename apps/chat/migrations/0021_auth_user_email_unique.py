from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0020_account_deletion_requests"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'CREATE UNIQUE INDEX "auth_user_email_lower_unique" '
                'ON "auth_user" (LOWER("email")) '
                "WHERE \"email\" <> ''"
            ),
            reverse_sql='DROP INDEX "auth_user_email_lower_unique"',
        ),
    ]
