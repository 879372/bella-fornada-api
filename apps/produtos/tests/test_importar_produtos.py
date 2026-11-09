from decimal import Decimal

from apps.produtos.management.commands.importar_produtos_legado import Command


def test_parse_decimal_accepts_brazilian_and_database_formats():
    command = Command()

    assert command.parse_decimal("1.234,56") == Decimal("1234.56")
    assert command.parse_decimal("1,234.56") == Decimal("1234.56")
    assert command.parse_decimal("6.50") == Decimal("6.50")
    assert command.parse_decimal("6,50") == Decimal("6.50")


def test_fiscal_code_preserves_leading_zeroes():
    command = Command()

    assert command._fiscal_code("0", 3) == "000"
    assert command._fiscal_code("60", 3) == "060"
    assert command._fiscal_code("7", 2) == "07"


def test_row_value_accepts_export_headers_with_or_without_accents():
    command = Command()

    assert command._row_value(
        {"Codigo da Mercadoria": "10"},
        "Código da Mercadoria",
        "Codigo da Mercadoria",
    ) == "10"
    assert command._row_value(
        {"Preço de Venda": "9,90"},
        "Preço de Venda",
        "Preco de Venda",
    ) == "9,90"
