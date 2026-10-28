from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('compras', '0004_alter_itemnotacompra_id_externo_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='notacompra',
            old_name='numero_nf',
            new_name='numero_documento',
        ),
        migrations.RemoveField(model_name='notacompra', name='api_source'),
        migrations.RemoveField(model_name='notacompra', name='chave_acesso'),
        migrations.RemoveField(model_name='notacompra', name='xml_nfe'),
    ]
