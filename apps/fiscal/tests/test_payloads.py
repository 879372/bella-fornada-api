from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.fiscal.services.errors import FiscalValidationError
from apps.fiscal.services.payloads import VendaFiscalPayloadBuilder


def make_item(**product_overrides):
    product_values = {
        "pk": 1,
        "codigo_legado": 10,
        "nome": "Produto fiscal",
        "ncm": "19059010",
        "cest": "1706200",
        "cfop": "5101",
        "cst_icms": "102",
        "cst_pis": "07",
        "cst_cofins": "07",
        "origem_mercadoria": "0",
        "codigo_beneficio_fiscal": "",
        "unidade_medida": "UN",
        "unidade_tributavel": "UN",
        "gtin_tributavel": "7891234567890",
        "aliquota_icms": Decimal("0"),
        "aliquota_pis": Decimal("0"),
        "aliquota_cofins": Decimal("0"),
    }
    product_values.update(product_overrides)
    product = SimpleNamespace(**product_values)
    return SimpleNamespace(
        produto=product,
        subtotal=Decimal("10.00"),
        quantidade=Decimal("2"),
    )


def test_item_payload_includes_optional_fiscal_classification():
    builder = VendaFiscalPayloadBuilder(
        SimpleNamespace(total_liquido=Decimal("10.00")), tipo="NFCE"
    )

    payload = builder._build_items([make_item()])[0]

    assert payload["cfop"] == "5101"
    assert payload["cest"] == "1706200"
    assert payload["cst_pis"] == "07"
    assert payload["cst_cofins"] == "07"
    assert payload["origem"] == "0"
    assert payload["gtin_tributavel"] == "7891234567890"


def test_item_payload_rejects_placeholder_ncm():
    builder = VendaFiscalPayloadBuilder(
        SimpleNamespace(total_liquido=Decimal("10.00")), tipo="NFCE"
    )

    with pytest.raises(FiscalValidationError, match="NCM válido"):
        builder._build_items([make_item(ncm="00000000")])
