import os
import django
from dotenv import load_dotenv

# Carrega o .env antes do setup do Django para pegar o banco de dados correto
load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from apps.vendas.models import Venda, SessaoCaixa, OperacaoCaixa
from apps.financeiro.models import ContaPagar, ContaReceber
from apps.compras.models import NotaCompra

print("---------------------------------")
print("INICIANDO LIMPEZA DE TRANSACOES...")

vendas_count = Venda.objects.all().count()
Venda.objects.all().delete()
print(f"- {vendas_count} Vendas deletadas.")

sangrias_count = OperacaoCaixa.objects.all().count()
OperacaoCaixa.objects.all().delete()
print(f"- {sangrias_count} Sangrias/Suprimentos deletados.")

sessoes_count = SessaoCaixa.objects.all().count()
SessaoCaixa.objects.all().delete()
print(f"- {sessoes_count} Sessoes de Caixa deletadas.")

pagar_count = ContaPagar.objects.all().count()
ContaPagar.objects.all().delete()
print(f"- {pagar_count} Contas a Pagar deletadas.")

receber_count = ContaReceber.objects.all().count()
ContaReceber.objects.all().delete()
print(f"- {receber_count} Contas a Receber deletadas.")

compras_count = NotaCompra.objects.all().count()
NotaCompra.objects.all().delete()
print(f"- {compras_count} Notas de Compra deletadas.")

print("---------------------------------")
print("✅ LIMPEZA CONCLUIDA! Banco pronto para Producao.")
print("✅ Produtos, Clientes e Usuarios foram mantidos intactos.")
