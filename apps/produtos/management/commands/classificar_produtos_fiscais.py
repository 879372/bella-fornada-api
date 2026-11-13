from django.core.management.base import BaseCommand

from apps.produtos.catalog_fiscal_rules import suggest_fiscal_fields
from apps.produtos.fiscal_review import catalog_checksum
from apps.produtos.management.commands.aplicar_produtos_fiscais import (
    Command as ApplyFiscalMappingCommand,
)
from apps.produtos.models import Produto


class Command(BaseCommand):
    help = 'Simula ou aplica a classificação fiscal inicial de todo o catálogo.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        mapping = {
            'versao': 1,
            'catalogo_checksum': catalog_checksum(),
            'fonte': (
                'Tabela NCM vigente da Receita Federal; tabelas EFD-Contribuições; '
                'Decreto RN 31.825/2022 para bebidas sujeitas a ST.'
            ),
            'observacao': (
                'Classificação inicial por família e descrição do produto. Registros de '
                'confiança baixa exigem conferência posterior com XML de compra ou ficha técnica.'
            ),
            'produtos': [
                {
                    'codigo_legado': product.codigo_legado,
                    'nome': product.nome,
                    'campos': suggest_fiscal_fields(product),
                }
                for product in Produto.all_objects.order_by('codigo_legado', 'pk').iterator()
            ],
        }
        command = ApplyFiscalMappingCommand()
        command.stdout = self.stdout
        command.stderr = self.stderr
        command._apply_mapping(mapping, apply=options['apply'])
