import json
import re
from collections import Counter
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.produtos.barcodes import gtin_valido
from apps.produtos.fiscal_codes import NORMAL_ICMS_CST, PIS_COFINS_CST, SIMPLES_CSOSN
from apps.produtos.fiscal_review import catalog_checksum, fiscal_snapshot
from apps.produtos.models import Produto


class Command(BaseCommand):
    help = 'Audita o cadastro fiscal de produtos sem alterar o banco.'

    def add_arguments(self, parser):
        parser.add_argument('--codigo', action='append', type=int, default=[])
        parser.add_argument('--detalhes', action='store_true')

    def handle(self, *args, **options):
        queryset = Produto.all_objects.order_by('codigo_legado')
        if options['codigo']:
            queryset = queryset.filter(codigo_legado__in=options['codigo'])

        summary = {
            'catalogo_checksum': catalog_checksum(),
            'total': queryset.count(),
            'ativos': queryset.filter(ativo=True).count(),
            'sem_ncm': queryset.filter(Q(ncm='') | Q(ncm='00000000')).count(),
            'sem_cst_pis': queryset.filter(cst_pis='').count(),
            'sem_cst_cofins': queryset.filter(cst_cofins='').count(),
            'nao_classificados': queryset.filter(
                tipo_origem_comercial=Produto.TipoOrigemComercial.NAO_CLASSIFICADO
            ).count(),
            'cfop_5405': queryset.filter(cfop='5405').count(),
            'cst_legado_060': queryset.filter(cst_icms='060').count(),
        }
        anomaly_counter = Counter()
        products_with_anomalies = 0
        for product in queryset.iterator():
            anomalies = self._anomalies(product)
            if anomalies:
                products_with_anomalies += 1
                anomaly_counter.update(anomalies)
        summary['produtos_com_anomalias'] = products_with_anomalies
        summary['anomalias'] = dict(sorted(anomaly_counter.items()))

        payload = {'resumo': summary}
        if options['detalhes'] or options['codigo']:
            payload['produtos'] = [
                {
                    'id_externo': str(product.id_externo),
                    'codigo_legado': product.codigo_legado,
                    'nome': product.nome,
                    'grupo': product.grupo,
                    'marca': product.marca,
                    'codigo_barras': product.codigo_barras,
                    'updated_at': product.updated_at.isoformat(),
                    'fiscal': fiscal_snapshot(product),
                    'anomalias': self._anomalies(product),
                }
                for product in queryset.iterator()
            ]
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

    @staticmethod
    def _anomalies(product):
        anomalies = []
        ncm = re.sub(r'\D', '', product.ncm or '')
        if len(ncm) != 8 or ncm == '00000000':
            anomalies.append('NCM_AUSENTE_OU_INVALIDO')
        cest = re.sub(r'\D', '', product.cest or '')
        if cest and len(cest) != 7:
            anomalies.append('CEST_INVALIDO')
        cfop = re.sub(r'\D', '', product.cfop or '')
        if len(cfop) != 4 or cfop[0] not in set('123567'):
            anomalies.append('CFOP_INVALIDO')
        if product.cst_icms not in SIMPLES_CSOSN | NORMAL_ICMS_CST:
            anomalies.append('CST_ICMS_OU_CSOSN_INVALIDO')
        if product.cst_pis not in PIS_COFINS_CST:
            anomalies.append('CST_PIS_AUSENTE_OU_INVALIDO')
        if product.cst_cofins not in PIS_COFINS_CST:
            anomalies.append('CST_COFINS_AUSENTE_OU_INVALIDO')
        if product.cst_icms == '060':
            anomalies.append('CST_060_LEGADO_EM_EMPRESA_SIMPLES')
        if product.cst_icms == '000':
            anomalies.append('CST_000_LEGADO_EM_EMPRESA_SIMPLES')
        if product.gtin_tributavel and not gtin_valido(product.gtin_tributavel):
            anomalies.append('GTIN_TRIBUTAVEL_INVALIDO')
        if product.fator_conversao_tributavel <= Decimal('0'):
            anomalies.append('FATOR_CONVERSAO_INVALIDO')
        if any(
            not Decimal('0') <= value <= Decimal('100')
            for value in (
                product.aliquota_icms,
                product.aliquota_pis,
                product.aliquota_cofins,
            )
        ):
            anomalies.append('ALIQUOTA_FORA_DA_FAIXA')
        if product.cfop == '5405' and product.tipo_origem_comercial == Produto.TipoOrigemComercial.NAO_CLASSIFICADO:
            anomalies.append('CFOP_5405_SEM_COMPROVACAO_ST')
        if product.tipo_origem_comercial == Produto.TipoOrigemComercial.NAO_CLASSIFICADO:
            anomalies.append('ORIGEM_COMERCIAL_NAO_CLASSIFICADA')
        if product.fiscal_confianca in {
            Produto.ConfiancaFiscal.ALTA,
            Produto.ConfiancaFiscal.MEDIA,
        } and not product.fiscal_fonte.strip():
            anomalies.append('REVISAO_SEM_FONTE')
        return anomalies
