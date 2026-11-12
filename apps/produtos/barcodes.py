from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class EtiquetaBalanca:
    codigo_produto: int
    quantidade_kg: Decimal


def _ean13_valido(codigo):
    if len(codigo) != 13 or not codigo.isdigit():
        return False
    total = sum(
        int(digito) * (1 if indice % 2 == 0 else 3)
        for indice, digito in enumerate(codigo[:12])
    )
    verificador = (10 - total % 10) % 10
    return verificador == int(codigo[-1])


def gtin_valido(codigo):
    """Valida GTIN-8/12/13/14 e rejeita códigos internos/variáveis."""
    codigo = ''.join(character for character in str(codigo or '') if character.isdigit())
    if len(codigo) not in {8, 12, 13, 14} or set(codigo) == {'0'}:
        return False
    # Prefixo 2 representa código de circulação restrita/etiqueta de balança.
    # O legado próprio da Bella Fornada usa 777 + seis zeros + código/DV; não
    # bloqueamos todo o prefixo GS1 777, que também pode ser legítimo.
    if codigo.startswith('2') or (
        len(codigo) == 13 and codigo.startswith('777000000')
    ):
        return False

    corpo, digito_verificador = codigo[:-1], int(codigo[-1])
    total = sum(
        int(digito) * (3 if indice % 2 == 0 else 1)
        for indice, digito in enumerate(reversed(corpo))
    )
    return (10 - total % 10) % 10 == digito_verificador


def interpretar_etiqueta_balanca(codigo):
    """Interpreta EAN-13 no formato 2 + PLU(5) + peso em gramas(6) + DV."""
    codigo = str(codigo or "").strip()
    if not codigo.startswith("2") or not _ean13_valido(codigo):
        return None

    codigo_produto = int(codigo[1:6])
    quantidade_kg = Decimal(codigo[6:12]) / Decimal("1000")
    if codigo_produto <= 0 or quantidade_kg <= 0:
        return None

    return EtiquetaBalanca(
        codigo_produto=codigo_produto,
        quantidade_kg=quantidade_kg,
    )
