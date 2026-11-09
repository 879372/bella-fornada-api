import csv
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.produtos.models import Produto, EstoqueLoja


class Command(BaseCommand):
    help = "Import products and stock from legacy CSV files - OPTIMIZED BATCH"

    def add_arguments(self, parser):
        parser.add_argument("--produtos-csv", type=str, default="produtos.csv")
        parser.add_argument("--estoque-csv", type=str, default="produtosLoja.csv")

    def parse_decimal(self, value):
        if not value:
            return Decimal("0.00")
        value = str(value).strip()
        if "," in value and "." in value:
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            value = value.replace(".", "").replace(",", ".")
        try:
            return Decimal(value)
        except InvalidOperation:
            return Decimal("0.00")

    def only_digits(self, value):
        return "".join(character for character in str(value or "") if character.isdigit())

    def _fiscal_code(self, value, length):
        digits = self.only_digits(value)
        return digits.zfill(length)[-length:] if digits else ""

    def _row_value(self, row, *names, default=""):
        for name in names:
            if name in row and row[name] not in (None, ""):
                return row[name]
        return default

    @transaction.atomic
    def handle(self, *args, **options):
        produtos_csv_path = options["produtos_csv"]
        estoque_csv_path = options["estoque_csv"]

        self.stdout.write(">> Reading Produtos...")
        produtos_to_create = []
        codigo_legado_set = set()

        with open(produtos_csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cod_legado_str = str(
                    self._row_value(row, "Código da Mercadoria", "Codigo da Mercadoria")
                ).strip()
                if not cod_legado_str or not cod_legado_str.isdigit():
                    continue
                cod_legado = int(cod_legado_str)

                if cod_legado in codigo_legado_set:
                    continue
                codigo_legado_set.add(cod_legado)

                nome = str(self._row_value(row, "Mercadoria")).strip()[:255]
                cod_barras = str(
                    self._row_value(row, "Cód Barra", "Cod Barra")
                ).strip()
                if cod_barras in ("0", "SEM GTIN", "NULL", ""):
                    cod_barras = None
                unidade = str(self._row_value(row, "Medida", default="UN")).strip()[:10] or "UN"
                preco_venda = self.parse_decimal(
                    self._row_value(row, "Preço de Venda", "Preco de Venda", default="0")
                )
                preco_compra = self.parse_decimal(
                    self._row_value(
                        row, "Preço Compra", "Preco Compra", "Preço C", default="0"
                    )
                )

                grupo = (row.get("Grupo", "") or "").strip()[:100]
                if grupo == "NULL":
                    grupo = ""
                subgrupo = (row.get("SubGrupo", "") or "").strip()[:100]
                if subgrupo == "NULL":
                    subgrupo = ""
                ativo_value = str(row.get("Ativo", "") or "").strip().upper()
                if ativo_value:
                    ativo = ativo_value in {"S", "SIM", "1", "TRUE"}
                else:
                    ativo = str(row.get("Desativado", "0") or "0").strip() != "1"

                marca = (row.get("Marca", "") or "").strip()[:100]
                ncm = self.only_digits(row.get("NCM", ""))
                if ncm == "00000000" or len(ncm) != 8:
                    ncm = ""
                cest = self.only_digits(row.get("CEST", ""))[:7]
                cfop = self.only_digits(row.get("CFOP", ""))[:4] or "5102"
                cst_icms = self._fiscal_code(
                    row.get("CST ICMS", row.get("CST/CSOSN", "")), 3
                ) or "102"
                cst_pis = self._fiscal_code(row.get("CST PIS", ""), 2)
                cst_cofins = self._fiscal_code(row.get("CST COFINS", ""), 2)
                origem = self._fiscal_code(row.get("Origem", "0"), 1) or "0"
                unidade_tributavel = (
                    row.get("Unidade Tributavel", "") or unidade
                ).strip()[:6]
                gtin_tributavel = self.only_digits(
                    row.get("GTIN Tributavel", "") or cod_barras
                )[:14]

                produtos_to_create.append(
                    Produto(
                        codigo_legado=cod_legado,
                        nome=nome,
                        codigo_barras=cod_barras,
                        preco_compra=preco_compra,
                        preco_venda=preco_venda,
                        unidade_medida=unidade,
                        grupo=grupo,
                        subgrupo=subgrupo,
                        marca=marca,
                        ativo=ativo,
                        ncm=ncm,
                        cest=cest,
                        cfop=cfop,
                        cst_icms=cst_icms,
                        cst_pis=cst_pis,
                        cst_cofins=cst_cofins,
                        origem_mercadoria=origem,
                        codigo_beneficio_fiscal=(
                            row.get("Codigo Beneficio Fiscal", "") or ""
                        ).strip()[:10],
                        unidade_tributavel=unidade_tributavel,
                        gtin_tributavel=gtin_tributavel,
                        fator_conversao_tributavel=self.parse_decimal(
                            row.get("Fator Conversao Tributavel", "1")
                        ) or Decimal("1"),
                        aliquota_icms=self.parse_decimal(row.get("Aliquota ICMS", "0")),
                        aliquota_pis=self.parse_decimal(row.get("Aliquota PIS", "0")),
                        aliquota_cofins=self.parse_decimal(row.get("Aliquota COFINS", "0")),
                    )
                )

        if produtos_to_create:
            # Apaga tudo antes para garantir recarga limpa no banco vazio
            Produto.objects.all().delete()
            self.stdout.write(
                f">> Bulk inserting {len(produtos_to_create)} products..."
            )
            Produto.objects.bulk_create(produtos_to_create, batch_size=500)
            self.stdout.write(
                self.style.SUCCESS(
                    f"   {len(produtos_to_create)} Produtos inserted successfully!"
                )
            )

        self.stdout.write(">> Reading EstoqueLoja...")
        # Recarrega os IDs recem criados
        produtos_db = {p.codigo_legado: p for p in Produto.objects.all()}

        estoque_to_create = []
        existing_estoques = set()

        with open(estoque_csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cod_legado_str = row.get("Código da Mercadoria", "").strip()
                loja = row.get("Loja", "").strip()
                if not cod_legado_str or not cod_legado_str.isdigit() or not loja:
                    continue

                cod_legado = int(cod_legado_str)
                if cod_legado not in produtos_db:
                    continue

                if (cod_legado, loja) in existing_estoques:
                    continue
                existing_estoques.add((cod_legado, loja))

                quantidade = self.parse_decimal(row.get("Estoque", "0"))
                estoque_to_create.append(
                    EstoqueLoja(
                        produto=produtos_db[cod_legado],
                        loja=loja,
                        quantidade=quantidade,
                    )
                )

        if estoque_to_create:
            EstoqueLoja.objects.all().delete()
            self.stdout.write(
                f">> Bulk inserting {len(estoque_to_create)} stock records..."
            )
            EstoqueLoja.objects.bulk_create(estoque_to_create, batch_size=500)
            self.stdout.write(
                self.style.SUCCESS(
                    f"   {len(estoque_to_create)} Estoque inserted successfully!"
                )
            )

        self.stdout.write(self.style.SUCCESS("All done!"))
