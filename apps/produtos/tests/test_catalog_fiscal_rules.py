import pytest

from apps.produtos.catalog_fiscal_rules import suggest_fiscal_fields
from apps.produtos.models import Produto


@pytest.mark.parametrize(
    ('nome', 'grupo', 'barcode', 'expected'),
    [
        ('PAO FRANCES', 'PADARIA', '7770000001408', ('19059090', '5101', '102', '')),
        ('COCA COLA LATA 350ML', 'BEBIDA', '7894900010015', ('22021000', '5405', '500', '0301002')),
        ('COCA COLA 2L', 'BEBIDA', '7894900027013', ('22021000', '5405', '500', '0301001')),
        ('MONSTER 473ML', 'BEBIDA', '070847022015', ('22029900', '5405', '500', '0301300')),
        ('GATORADE UVA 500ML', 'BEBIDA', '7892840808051', ('22029900', '5405', '500', '0301500')),
        ('AGUA MINERAL 500ML', 'BEBIDA', '7898005516175', ('22011000', '5405', '500', '0300600')),
        ('CAFE SOLUVEL SANTA CLARA 40G', 'CEREAIS', '7896045112968', ('21011110', '5102', '102', '')),
        ('BISCOITO WAFER CHOCOLATE', 'BOMBONIERE', '7896213006044', ('19053200', '5102', '102', '')),
        ('TAPIOCA COM FRANGO', 'COZINHA', '7770000007356', ('19030000', '5101', '102', '')),
        ('DETERGENTE LIMPOL 500ML', 'HIGIENE', '7891022639001', ('34025000', '5102', '102', '')),
    ],
)
def test_catalog_rules(nome, grupo, barcode, expected):
    product = Produto(
        nome=nome,
        grupo=grupo,
        codigo_barras=barcode,
        unidade_medida='UN',
    )

    fields = suggest_fiscal_fields(product)

    assert (
        fields['ncm'], fields['cfop'], fields['cst_icms'], fields['cest']
    ) == expected


def test_unknown_resale_is_marked_low_confidence():
    product = Produto(nome='PRODUTO SEM DETALHE', grupo='DIVERSOS')

    fields = suggest_fiscal_fields(product)

    assert fields['tipo_origem_comercial'] == Produto.TipoOrigemComercial.REVENDA
    assert fields['fiscal_confianca'] == Produto.ConfiancaFiscal.BAIXA
    assert 'provisório' in fields['fiscal_observacao']
