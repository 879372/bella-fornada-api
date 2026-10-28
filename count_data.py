import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

with connection.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM produtos_produto")
    count_prod = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM vendas_venda")
    count_venda = cursor.fetchone()[0]
    print(f"Products: {count_prod}, Sales: {count_venda}")
