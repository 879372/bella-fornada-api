from django.db import models
from apps.core.models import BaseModel, ActiveManager

class Cliente(BaseModel):
    PESSOA_FISICA = 'F'
    PESSOA_JURIDICA = 'J'
    TIPO_PESSOA = [(PESSOA_FISICA, 'Física'), (PESSOA_JURIDICA, 'Jurídica')]

    codigo_legado = models.IntegerField(unique=True, null=True, blank=True)
    razao_social = models.CharField(max_length=255, blank=True)
    nome = models.CharField(max_length=255)

    # Endereço
    endereco = models.CharField(max_length=255, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    uf = models.CharField(max_length=2, blank=True, null=True)
    cep = models.CharField(max_length=10, blank=True, null=True)

    # Contato
    telefone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)

    # Identificação e endereço
    cpf_cnpj = models.CharField(max_length=20, blank=True, null=True)
    inscricao_estadual = models.CharField(max_length=30, blank=True, null=True)
    pessoa = models.CharField(max_length=1, choices=TIPO_PESSOA, default=PESSOA_FISICA)
    regime_tributario = models.IntegerField(default=0)

    # Dados complementares
    tipo_cliente = models.CharField(max_length=50, blank=True, null=True)
    data_cadastro = models.DateTimeField(null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_aberto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    observacoes = models.TextField(blank=True, null=True)
    ativo = models.BooleanField(default=True)
    loja = models.CharField(max_length=50, blank=True, null=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'clientes'

    def __str__(self):
        return f"{self.codigo_legado} - {self.nome}"
