from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('vendas', '0011_alter_venda_status'),
    ]

    operations = [
        migrations.RemoveField(model_name='venda', name='nf_chave'),
        migrations.RemoveField(model_name='venda', name='nf_emitida'),
        migrations.RemoveField(model_name='venda', name='nf_id_fiscal'),
        migrations.RemoveField(model_name='venda', name='nf_mensagem'),
        migrations.RemoveField(model_name='venda', name='nf_numero'),
        migrations.RemoveField(model_name='venda', name='nf_protocolo'),
        migrations.RemoveField(model_name='venda', name='nf_qr_code'),
        migrations.RemoveField(model_name='venda', name='nf_serie'),
        migrations.RemoveField(model_name='venda', name='nf_status'),
        migrations.RemoveField(model_name='venda', name='nf_tipo'),
        migrations.RemoveField(model_name='venda', name='nf_url_pdf'),
    ]
