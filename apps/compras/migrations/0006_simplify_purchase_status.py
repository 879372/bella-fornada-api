from django.db import migrations, models


def mark_purchases_as_registered(apps, schema_editor):
    NotaCompra = apps.get_model('compras', 'NotaCompra')
    NotaCompra.objects.exclude(status='RECEBIDA').update(status='RECEBIDA')


class Migration(migrations.Migration):
    dependencies = [
        ('compras', '0005_remove_fiscal_fields'),
    ]

    operations = [
        migrations.RunPython(mark_purchases_as_registered, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='notacompra',
            name='status',
            field=models.CharField(choices=[('RECEBIDA', 'Registrada')], default='RECEBIDA', max_length=10),
        ),
    ]
