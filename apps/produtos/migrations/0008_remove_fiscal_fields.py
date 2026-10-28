from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('produtos', '0007_alter_estoqueloja_id_externo_alter_grupo_id_externo_and_more'),
    ]

    operations = [
        migrations.RemoveField(model_name='produto', name='cest'),
        migrations.RemoveField(model_name='produto', name='cfop_padrao'),
        migrations.RemoveField(model_name='produto', name='ncm'),
        migrations.RemoveField(model_name='produto', name='origem'),
    ]
