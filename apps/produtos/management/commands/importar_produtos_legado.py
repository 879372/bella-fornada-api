import csv
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.produtos.models import Produto, EstoqueLoja

class Command(BaseCommand):
    help = 'Import products and stock from legacy CSV files - OPTIMIZED BATCH'

    def add_arguments(self, parser):
        parser.add_argument('--produtos-csv', type=str, default='produtos.csv')
        parser.add_argument('--estoque-csv', type=str, default='produtosLoja.csv')

    def parse_decimal(self, value):
        if not value: return Decimal('0.00')
        value = str(value).strip().replace('.', '').replace(',', '.')
        try: return Decimal(value)
        except InvalidOperation: return Decimal('0.00')

    @transaction.atomic
    def handle(self, *args, **options):
        produtos_csv_path = options['produtos_csv']
        estoque_csv_path = options['estoque_csv']

        self.stdout.write(">> Reading Produtos...")
        produtos_to_create = []
        codigo_legado_set = set()


        with open(produtos_csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cod_legado_str = row.get('Código da Mercadoria', '').strip()
                if not cod_legado_str or not cod_legado_str.isdigit(): continue
                cod_legado = int(cod_legado_str)

                if cod_legado in codigo_legado_set:
                    continue
                codigo_legado_set.add(cod_legado)

                nome = row.get('Mercadoria', '').strip()[:255]
                cod_barras = row.get('Cód Barra', '').strip()
                if cod_barras in ('0', 'SEM GTIN', 'NULL', ''): cod_barras = None
                unidade = row.get('Medida', 'UN').strip()[:10] or 'UN'
                preco_venda = self.parse_decimal(row.get('Preço de Venda', '0'))
                preco_compra = self.parse_decimal(row.get('Preço Compra', row.get('Preço C', '0')))

                grupo = (row.get('Grupo', '') or '').strip()[:100]
                if grupo == 'NULL': grupo = ''
                subgrupo = (row.get('SubGrupo', '') or '').strip()[:100]
                if subgrupo == 'NULL': subgrupo = ''
                ativo = False if row.get('Desativado', '0').strip() == '1' else True

                produtos_to_create.append(Produto(
                    codigo_legado=cod_legado,
                    nome=nome,
                    codigo_barras=cod_barras,
                    preco_compra=preco_compra,
                    preco_venda=preco_venda,
                    unidade_medida=unidade,
                    grupo=grupo,
                    subgrupo=subgrupo,
                    ativo=ativo,
                ))

        if produtos_to_create:
            # Apaga tudo antes para garantir recarga limpa no banco vazio
            Produto.objects.all().delete()
            self.stdout.write(f">> Bulk inserting {len(produtos_to_create)} products...")
            Produto.objects.bulk_create(produtos_to_create, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"   {len(produtos_to_create)} Produtos inserted successfully!"))

        self.stdout.write(">> Reading EstoqueLoja...")
        # Recarrega os IDs recem criados
        produtos_db = {p.codigo_legado: p for p in Produto.objects.all()}

        estoque_to_create = []
        existing_estoques = set()

        with open(estoque_csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cod_legado_str = row.get('Código da Mercadoria', '').strip()
                loja = row.get('Loja', '').strip()
                if not cod_legado_str or not cod_legado_str.isdigit() or not loja: continue

                cod_legado = int(cod_legado_str)
                if cod_legado not in produtos_db: continue

                if (cod_legado, loja) in existing_estoques: continue
                existing_estoques.add((cod_legado, loja))

                quantidade = self.parse_decimal(row.get('Estoque', '0'))
                estoque_to_create.append(EstoqueLoja(
                    produto=produtos_db[cod_legado],
                    loja=loja,
                    quantidade=quantidade
                ))

        if estoque_to_create:
            EstoqueLoja.objects.all().delete()
            self.stdout.write(f">> Bulk inserting {len(estoque_to_create)} stock records...")
            EstoqueLoja.objects.bulk_create(estoque_to_create, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"   {len(estoque_to_create)} Estoque inserted successfully!"))

        self.stdout.write(self.style.SUCCESS("All done!"))
