from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.fiscal.services.errors import FiscalValidationError
from apps.fiscal.services.payloads import VendaFiscalPayloadBuilder


def item(**overrides):
    values = dict(pk=1, codigo_legado=10, nome="Produto fiscal", ncm="19059010",
                  cest="1706200", cfop="5101", cst_icms="102", cst_pis="07",
                  cst_cofins="07", origem_mercadoria="0", codigo_beneficio_fiscal="",
                  unidade_medida="UN", codigo_barras="7896045112968",
                  unidade_tributavel="UN", gtin_tributavel="7896045112968",
                  fator_conversao_tributavel=1,
                  aliquota_icms=0, aliquota_pis=0, aliquota_cofins=0,
                  fiscal_confianca="ALTA")
    values.update(overrides)
    return SimpleNamespace(produto=SimpleNamespace(**values), subtotal=Decimal("10.00"),
                           quantidade=Decimal("2"), preco_unitario=Decimal("5.00"))


def builder(product_item):
    items = SimpleNamespace(select_related=lambda *_: [product_item])
    sale = SimpleNamespace(itens=items, desconto=0, taxa_entrega=0)
    config = SimpleNamespace(codigo_regime_tributario="1")
    result = object.__new__(VendaFiscalPayloadBuilder)
    result.venda, result.config = sale, config
    return result


def test_item_payload_uses_geranet_field_names():
    payload = builder(item())._items()[0]
    assert payload["ncmProduto"] == "19059010"
    assert payload["cfop"] == "5101"
    assert payload["icmsCsosn"] == "102"
    assert payload["eanProduto"] == "7896045112968"
    assert payload["unidadeTributavel"] == "UN"
    assert payload["quantidadeTributavel"] == Decimal("2.0000")
    assert payload["valorUnitarioTributavel"] == Decimal("5.0000000000")


def test_item_payload_rejects_placeholder_ncm():
    with pytest.raises(FiscalValidationError, match="NCM válido"):
        builder(item(ncm="00000000"))._items()


@pytest.mark.parametrize('invalid_cst', ['', '00'])
def test_item_payload_rejects_missing_or_invalid_pis_cofins_cst(invalid_cst):
    with pytest.raises(FiscalValidationError, match="CST PIS"):
        builder(item(cst_pis=invalid_cst))._items()


def test_item_payload_rejects_legacy_cst_as_csosn():
    with pytest.raises(FiscalValidationError, match="CSOSN válido"):
        builder(item(cst_icms="000"))._items()


def test_item_payload_rejects_product_without_approved_fiscal_review():
    with pytest.raises(FiscalValidationError, match="revisão fiscal aprovada"):
        builder(item(fiscal_confianca="NAO_REVISADO"))._items()


def test_item_payload_ignores_internal_and_scale_codes_as_gtin():
    payload = builder(item(gtin_tributavel="", codigo_barras="7770000001408"))._items()[0]
    assert payload["eanProduto"] == "SEM GTIN"

    payload = builder(item(gtin_tributavel="", codigo_barras="2001490000844"))._items()[0]
    assert payload["eanProduto"] == "SEM GTIN"


def test_item_payload_prefers_valid_commercial_gtin():
    payload = builder(item(
        codigo_barras="7896045112968",
        gtin_tributavel="7898080640413",
    ))._items()[0]
    assert payload["eanProduto"] == "7896045112968"

def test_item_payload_applies_taxable_unit_conversion():
    payload = builder(item(
        unidade_medida="CX",
        unidade_tributavel="UN",
        fator_conversao_tributavel=12,
    ))._items()[0]
    assert payload["quantidadeTributavel"] == Decimal("24.0000")
    assert payload["valorUnitarioTributavel"] == Decimal("0.4166666667")


def test_payment_payload_uses_current_geranet_field_names():
    result = builder(item())
    result.venda.pagamentos = SimpleNamespace(all=lambda: [
        SimpleNamespace(forma="PIX", valor=Decimal("10.00")),
    ])
    result.venda.total_liquido = Decimal("8.00")

    payload = result._payments()

    assert payload == {
        "troco": Decimal("2.00"),
        "detalhamento": [{
            "tipo": "17",
            "valor": Decimal("10.00"),
            "indicadorPagamento": "0",
        }],
    }
