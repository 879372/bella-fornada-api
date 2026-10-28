import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime
import pytz
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.clientes.models import Cliente

TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

class Command(BaseCommand):
    help = 'Importa clientes do CSV legado em lote'

    def add_arguments(self, parser):
        parser.add_argument('--csv', type=str, default='clientes.csv')

    def parse_decimal(self, value):
        if not value or value.strip() == 'NULL': return Decimal('0.00')
        try: return Decimal(str(value).strip().replace('.', '').replace(',', '.'))
        except InvalidOperation: return Decimal('0.00')

    def parse_date(self, value, with_time=False):
        if not value or value.strip() in ('NULL', ''):
            return None
        value = value.strip().split('.')[0]
        fmts = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
        for fmt in fmts:
            try:
                dt = datetime.strptime(value, fmt)
                return TIMEZONE_BR.localize(dt)
            except ValueError:
                continue
        return None

    def clean(self, value, fallback=''):
        if not value or str(value).strip() in ('NULL', '0', ''): return fallback
        return str(value).strip()

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = options['csv']
        clientes_to_create = []
        codigos_vistos = set()

        self.stdout.write(f">> Lendo {csv_path}...")

        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cod_str = row.get('Código do Cliente', '').strip()
                if not cod_str or not cod_str.isdigit(): continue
                cod = int(cod_str)
                if cod in codigos_vistos: continue
                codigos_vistos.add(cod)

                cpf_cnpj = self.clean(row.get('CGC'))
                if cpf_cnpj in ('00000000000', '00000000000000'): cpf_cnpj = None

                email = self.clean(row.get('E-mail'))
                if email and '@' not in email: email = None

                uf = self.clean(row.get('UF'))[:2] if self.clean(row.get('UF')) else None

                clientes_to_create.append(Cliente(
                    codigo_legado=cod,
                    razao_social=self.clean(row.get('Razão Social'))[:255],
                    nome=self.clean(row.get('Nome do Cliente'), 'SEM NOME')[:255],
                    endereco=self.clean(row.get('Endereço'))[:255] or None,
                    bairro=self.clean(row.get('Bairro'))[:100] or None,
                    cidade=self.clean(row.get('Cidade'))[:100] or None,
                    uf=uf,
                    cep=self.clean(row.get('CEP'))[:10] or None,
                    telefone=self.clean(row.get('Fone Resid'))[:30] or None,
                    email=email[:255] if email else None,
                    cpf_cnpj=cpf_cnpj[:20] if cpf_cnpj else None,
                    inscricao_estadual=self.clean(row.get('Inscrição Estadual'))[:30] or None,
                    pessoa=self.clean(row.get('Pessoa'), 'F')[:1],
                    regime_tributario=int(self.clean(row.get('RegimeTributario'), '0') or '0'),
                    tipo_cliente=self.clean(row.get('Tipo de Cliente'))[:50] or None,
                    data_cadastro=self.parse_date(row.get('Dt Cadastro'), with_time=True),
                    data_nascimento=self.parse_date(row.get('Datanasc')),
                    limite_credito=self.parse_decimal(row.get('Limite Crédito')),
                    valor_aberto=self.parse_decimal(row.get('valor aberto')),
                    observacoes=self.clean(row.get('Observações')) or None,
                    ativo=False if self.clean(row.get('Desativado')) == '1' else True,
                    loja=self.clean(row.get('Loja'))[:50] or None,
                ))

        Cliente.objects.all().delete()
        self.stdout.write(f">> Inserindo {len(clientes_to_create)} clientes em lote...")
        Cliente.objects.bulk_create(clientes_to_create, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"   {len(clientes_to_create)} clientes importados com sucesso!"))
