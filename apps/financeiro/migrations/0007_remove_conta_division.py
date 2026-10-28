from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('financeiro', '0006_add_conta_to_financeiro'),
    ]

    operations = [
        migrations.RemoveField(model_name='contapagar', name='conta'),
        migrations.RemoveField(model_name='contareceber', name='conta'),
    ]
