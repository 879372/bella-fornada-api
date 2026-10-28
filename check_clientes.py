import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

with connection.cursor() as cursor:
    cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'clientes_cliente' AND column_name = 'id'")
    row = cursor.fetchone()
    print(f"Clientes ID type: {row}")
