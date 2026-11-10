from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.fiscal.services.errors import FiscalValidationError
from apps.fiscal.services.payloads import VendaFiscalPayloadBuilder


def item(**overrides):
    values = dict(pk=1, codigo_legado=10, nome="Produto fiscal", ncm="19059010",
                  cest="1706200", cfop="5101", cst_icms="102", cst_pis="07",
                  cst_cofins="07", origem_mercadoria="0", codigo_beneficio_fiscal="",
                  unidade_medida="UN", codigo_barras="7891234567890",
                  aliquota_icms=0, aliquota_pis=0, aliquota_cofins=0)
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
    assert payload["eanProduto"] == "7891234567890"


def test_item_payload_rejects_placeholder_ncm():
    with pytest.raises(FiscalValidationError, match="NCM válido"):
        builder(item(ncm="00000000"))._items()
