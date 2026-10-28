from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('compras', '0001_initial'),
    ]

    # The fields were already created by 0001_initial. Keeping this migration
    # as a no-op preserves the migration graph without duplicating columns on
    # fresh PostgreSQL databases.
    operations = []
