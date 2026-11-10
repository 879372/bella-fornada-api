import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fiscal", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ConfiguracaoFiscal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id_externo", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("ambiente", models.CharField(choices=[("homologacao", "Homologação"), ("producao", "Produção")], default="homologacao", max_length=12)),
                ("api_url", models.URLField(default="https://nfe.geranet.net/api/v1")),
                ("api_key_encrypted", models.TextField(blank=True)),
                ("certificado_encrypted", models.TextField(blank=True)),
                ("certificado_nome", models.CharField(blank=True, max_length=255)),
                ("certificado_senha_encrypted", models.TextField(blank=True)),
                ("cnpj", models.CharField(blank=True, max_length=14)),
                ("inscricao_estadual", models.CharField(blank=True, max_length=30)),
                ("razao_social", models.CharField(blank=True, max_length=200)),
                ("nome_fantasia", models.CharField(blank=True, max_length=60)),
                ("telefone", models.CharField(blank=True, max_length=20)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("logradouro", models.CharField(blank=True, max_length=200)),
                ("numero", models.CharField(blank=True, max_length=20)),
                ("complemento", models.CharField(blank=True, max_length=100)),
                ("bairro", models.CharField(blank=True, max_length=100)),
                ("municipio", models.CharField(blank=True, max_length=100)),
                ("codigo_municipio", models.CharField(blank=True, max_length=7)),
                ("uf", models.CharField(blank=True, max_length=2)),
                ("cep", models.CharField(blank=True, max_length=8)),
                ("codigo_regime_tributario", models.CharField(default="1", max_length=1)),
                ("tipo_atividade", models.CharField(default="3", max_length=1)),
                ("serie_nfce", models.CharField(default="1", max_length=3)),
                ("proximo_numero_nfce", models.PositiveIntegerField(default=1)),
                ("serie_nfe", models.CharField(default="1", max_length=3)),
                ("proximo_numero_nfe", models.PositiveIntegerField(default=1)),
                ("csc_encrypted", models.TextField(blank=True)),
                ("csc_id", models.CharField(blank=True, max_length=10)),
            ],
            options={"verbose_name": "Configuração fiscal", "verbose_name_plural": "Configurações fiscais"},
        )
    ]
