"""Arquivos de carga do MGV (Toledo): ITENSMGV.TXT e DEPTO.TXT.

O layout segue exatamente os arquivos gerados pelo sistema legado da loja:
linhas de largura fixa, codificação Windows-1252 e quebra de linha CRLF.

ITENSMGV.TXT (150 posições por linha):
    01-02  departamento
    03     tipo (0 = peso, 1 = unidade, 2 = tipo 2 do legado)
    04-09  código do item (PLU)
    10-15  preço em centavos (R$/kg nos itens por peso)
    16-18  validade em dias
    19-68  descritivo (50 caracteres)
    69-150 campos complementares (informação extra, imagem, nutricional,
           flags de impressão de validade/embalagem e demais códigos), que o
           legado envia sempre zerados, exceto as duas flags de impressão.

DEPTO.TXT (42 posições): código do departamento (2) + descrição (40).
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

ENCODING = 'cp1252'
EOL = b'\r\n'
TAMANHO_DESCRITIVO = 50
COMPLEMENTO = '0' * 16 + '11' + '0' * 64
TAMANHO_LINHA_ITENS = 18 + TAMANHO_DESCRITIVO + len(COMPLEMENTO)
TAMANHO_DESCRICAO_DEPTO = 40


class ErroCargaBalanca(ValueError):
    pass


@dataclass(frozen=True)
class ItemMGV:
    departamento: int
    tipo: str
    codigo: int
    preco: Decimal
    validade_dias: int
    descritivo: str


def _numero(valor: int, tamanho: int, campo: str, referencia: str) -> str:
    if valor < 0 or len(str(valor)) > tamanho:
        raise ErroCargaBalanca(f'{referencia}: {campo} {valor} não cabe em {tamanho} dígitos.')
    return str(valor).zfill(tamanho)


def _texto(valor: str, tamanho: int) -> str:
    # Mantém espaços internos/iniciais como o legado; só neutraliza quebras de linha.
    texto = (valor or '').upper().replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').rstrip()
    texto = texto.encode(ENCODING, errors='replace').decode(ENCODING)
    return texto[:tamanho].ljust(tamanho)


def linha_item(item: ItemMGV) -> bytes:
    ref = f'Item {item.codigo}'
    if item.tipo not in {'0', '1', '2'}:
        raise ErroCargaBalanca(f'{ref}: tipo de balança inválido ({item.tipo!r}).')
    centavos = int((item.preco * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    linha = (
        _numero(item.departamento, 2, 'departamento', ref)
        + item.tipo
        + _numero(item.codigo, 6, 'código', ref)
        + _numero(centavos, 6, 'preço em centavos', ref)
        + _numero(item.validade_dias, 3, 'validade', ref)
        + _texto(item.descritivo, TAMANHO_DESCRITIVO)
        + COMPLEMENTO
    )
    return linha.encode(ENCODING)


def gerar_itensmgv(itens) -> bytes:
    return b''.join(linha_item(item) + EOL for item in sorted(itens, key=lambda i: i.codigo))


def gerar_depto(departamentos) -> bytes:
    """`departamentos` é uma sequência de (código, descrição)."""
    linhas = []
    for codigo, descricao in sorted(departamentos):
        linha = _numero(codigo, 2, 'departamento', 'Departamento') + _texto(
            descricao, TAMANHO_DESCRICAO_DEPTO
        )
        linhas.append(linha.encode(ENCODING) + EOL)
    return b''.join(linhas)


def ler_itensmgv(conteudo: bytes) -> list[ItemMGV]:
    itens = []
    codigos = set()
    for numero, bruta in enumerate(conteudo.splitlines(), start=1):
        if not bruta.strip():
            continue
        linha = bruta.decode(ENCODING, errors='replace')
        if (len(linha) != TAMANHO_LINHA_ITENS
                or not linha[:18].isascii() or not linha[:18].isdigit()
                or linha[2] not in {'0', '1', '2'}
                or not linha[68:].isascii() or not linha[68:].isdigit()):
            raise ErroCargaBalanca(f'Linha {numero} fora do layout ITENSMGV.')
        codigo = int(linha[3:9])
        if codigo <= 0 or codigo in codigos:
            raise ErroCargaBalanca(f'Linha {numero}: código {codigo} inválido ou repetido.')
        codigos.add(codigo)
        itens.append(ItemMGV(
            departamento=int(linha[0:2]),
            tipo=linha[2],
            codigo=codigo,
            preco=Decimal(int(linha[9:15])) / 100,
            validade_dias=int(linha[15:18]),
            descritivo=linha[18:18 + TAMANHO_DESCRITIVO].rstrip(),
        ))
    if not itens:
        raise ErroCargaBalanca('O arquivo ITENSMGV está vazio.')
    return itens


def item_do_produto(produto, configuracao) -> ItemMGV:
    tipo = produto.tipo_balanca or (
        '0' if (produto.unidade_medida or '').upper() == 'KG' else '1'
    )
    validade = produto.validade_balanca_dias
    if validade is None:
        validade = configuracao.validade_padrao_dias
    if produto.codigo_legado is None:
        raise ErroCargaBalanca(f'Produto "{produto.nome}" está sem código para a balança.')
    return ItemMGV(
        departamento=configuracao.departamento,
        tipo=tipo,
        codigo=produto.codigo_legado,
        preco=produto.preco_venda,
        validade_dias=validade,
        descritivo=produto.nome,
    )
