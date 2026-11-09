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
