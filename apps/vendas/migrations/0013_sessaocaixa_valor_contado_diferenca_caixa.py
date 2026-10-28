from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('vendas', '0012_remove_fiscal_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessaocaixa',
            name='valor_contado',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='sessaocaixa',
            name='diferenca_caixa',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
