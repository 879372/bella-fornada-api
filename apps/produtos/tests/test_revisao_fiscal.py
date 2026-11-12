import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.produtos.fiscal_review import catalog_checksum
from apps.produtos.models import LoteRevisaoFiscal, Produto
from apps.produtos.tests.factories import ProdutoFactory


@pytest.mark.django_db
def test_fiscal_mapping_is_dry_run_by_default_and_supports_rollback(tmp_path):
    product = ProdutoFactory(
        codigo_legado=140,
        nome='PAO KG',
        ncm='',
        cfop='5102',
        cst_icms='102',
        cst_pis='',
        cst_cofins='',
    )
    mapping = {
        'versao': 1,
        'catalogo_checksum': catalog_checksum(),
        'fonte': 'Receita Federal e revisão da operação interna',
        'produtos': [{
            'codigo_legado': 140,
            'nome': 'PAO KG',
            'campos': {
                'ncm': '19059090',
                'cest': '',
                'cfop': '5101',
                'cst_icms': '102',
                'cst_pis': '49',
                'cst_cofins': '49',
                'origem_mercadoria': '0',
                'unidade_tributavel': 'KG',
                'gtin_tributavel': '',
                'fator_conversao_tributavel': '1',
                'aliquota_icms': '0',
                'aliquota_pis': '0',
                'aliquota_cofins': '0',
                'tipo_origem_comercial': 'FABRICACAO_PROPRIA',
                'fiscal_confianca': 'ALTA',
                'fiscal_fonte': 'Solução de Consulta RFB para pão francês',
                'fiscal_observacao': 'Classificação revisada para homologação.',
            },
        }],
    }
    mapping_path = tmp_path / 'mapping.json'
    mapping_path.write_text(json.dumps(mapping), encoding='utf-8')

    output = StringIO()
    call_command('aplicar_produtos_fiscais', str(mapping_path), stdout=output)
    product.refresh_from_db()
    assert product.ncm == ''
    assert LoteRevisaoFiscal.objects.count() == 0
    assert 'SIMULACAO' in output.getvalue()

    output = StringIO()
    call_command('aplicar_produtos_fiscais', str(mapping_path), apply=True, stdout=output)
    product.refresh_from_db()
    batch = LoteRevisaoFiscal.objects.get()
    assert product.ncm == '19059090'
    assert product.cfop == '5101'
    assert product.cst_pis == '49'
    assert product.tipo_origem_comercial == Produto.TipoOrigemComercial.FABRICACAO_PROPRIA
    assert batch.itens.count() == 1

    call_command('aplicar_produtos_fiscais', rollback=str(batch.id_externo))
    product.refresh_from_db()
    assert product.ncm == '19059090'

    call_command('aplicar_produtos_fiscais', rollback=str(batch.id_externo), apply=True)
    product.refresh_from_db()
    batch.refresh_from_db()
    assert product.ncm == ''
    assert product.cfop == '5102'
    assert batch.status == LoteRevisaoFiscal.Status.REVERTIDO


@pytest.mark.django_db
def test_fiscal_mapping_aborts_when_catalog_changed(tmp_path):
    product = ProdutoFactory(codigo_legado=1, nome='PRODUTO')
    mapping = {
        'versao': 1,
        'catalogo_checksum': catalog_checksum(),
        'produtos': [{
            'codigo_legado': 1,
            'nome': 'PRODUTO',
            'campos': {'cst_pis': '49'},
        }],
    }
    path = tmp_path / 'mapping.json'
    path.write_text(json.dumps(mapping), encoding='utf-8')
    product.nome = 'PRODUTO ALTERADO'
    product.save(update_fields=['nome', 'updated_at'])

    with pytest.raises(CommandError, match='catálogo mudou'):
        call_command('aplicar_produtos_fiscais', str(path), apply=True)

    assert LoteRevisaoFiscal.objects.count() == 0


@pytest.mark.django_db
def test_rollback_accepts_equivalent_decimal_scale(tmp_path):
    product = ProdutoFactory(
        codigo_legado=2,
        nome='PRODUTO FRACIONADO',
        ncm='19059090',
        cst_pis='49',
        cst_cofins='49',
    )
    mapping = {
        'versao': 1,
        'catalogo_checksum': catalog_checksum(),
        'produtos': [{
            'codigo_legado': 2,
            'nome': product.nome,
            'campos': {'fator_conversao_tributavel': '12'},
        }],
    }
    path = tmp_path / 'decimal.json'
    path.write_text(json.dumps(mapping), encoding='utf-8')

    call_command('aplicar_produtos_fiscais', str(path), apply=True)
    batch = LoteRevisaoFiscal.objects.get()
    product.refresh_from_db()
    assert product.fator_conversao_tributavel == 12

    call_command('aplicar_produtos_fiscais', rollback=str(batch.id_externo), apply=True)
    product.refresh_from_db()
    assert product.fator_conversao_tributavel == 1


@pytest.mark.django_db
def test_apply_requires_catalog_checksum_and_does_not_create_empty_batch(tmp_path):
    product = ProdutoFactory(codigo_legado=3, nome='SEM ALTERACAO', cst_pis='49')
    mapping = {
        'versao': 1,
        'produtos': [{
            'codigo_legado': 3,
            'nome': product.nome,
            'campos': {'cst_pis': '49'},
        }],
    }
    path = tmp_path / 'no-checksum.json'
    path.write_text(json.dumps(mapping), encoding='utf-8')
    with pytest.raises(CommandError, match='catalogo_checksum'):
        call_command('aplicar_produtos_fiscais', str(path), apply=True)

    mapping['catalogo_checksum'] = catalog_checksum()
    path.write_text(json.dumps(mapping), encoding='utf-8')
    call_command('aplicar_produtos_fiscais', str(path), apply=True)
    assert LoteRevisaoFiscal.objects.count() == 0
