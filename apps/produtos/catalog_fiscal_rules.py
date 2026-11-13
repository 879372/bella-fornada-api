import re
import unicodedata

from .barcodes import gtin_valido
from .models import Produto


RFB_NCM_SOURCE = (
    'https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/'
    'classificacao-fiscal-de-mercadorias/download-ncm-nomenclatura-comum-do-mercosul'
)
RN_ST_SOURCE = 'Decreto RN 31.825/2022, Anexo 010 (Convênio ICMS 142/2018)'
SPED_SOURCE = (
    'https://www.gov.br/sped/pt-br/assuntos/escrituracoes-digitais/'
    'efd-contribuicoes/tabelas-de-codigos'
)


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(character for character in text if not unicodedata.combining(character))
    return re.sub(r'[^A-Z0-9]+', ' ', text.upper()).strip()


def contains_any(text, terms):
    return any(term in text for term in terms)


def _is_own_production(product, name, group):
    if 'REVENDA' in name:
        return False
    resale_in_padaria = {
        'PEITO DE PERU', 'PRESUNTO', 'PRESUNTO FATIA', 'SALSICHA', 'NATA',
        'MANTEIGA', 'QUEIJO MANTEIGA', 'QUEIJO MUSSARELA', 'QUEIJO COALHO',
        'MUSSARELA FATIA',
    }
    if group == 'PADARIA' and (
        name in resale_in_padaria or name.startswith(('MORT ', 'MORTADELA'))
    ):
        return False
    if group in {'PADARIA', 'COZINHA', 'CONFEITARIA'}:
        barcode = re.sub(r'\D', '', product.codigo_barras or '')
        internal = barcode.startswith(('2', '777000', '750043', '789800551'))
        packaged = bool(re.search(r'\b\d+\s?(G|KG|ML|L)\b', name))
        if packaged and barcode and gtin_valido(barcode) and not internal:
            return False
        return True
    return contains_any(name, ('BUFFET', 'CAFE DA MANHA'))


def _beverage_st(name, group):
    if group not in {'BEBIDA', 'CONVENIENCIA', 'DIVERSOS'}:
        return None
    if contains_any(name, ('MONSTER', 'REDBULL', 'RED BULL', 'BALY', 'INFINITY ENERGY')):
        return ('22029900', '0301300', 'bebida energética sujeita a ST no RN')
    if 'GATORADE' in name:
        return ('22029900', '0301500', 'bebida hidroeletrolítica sujeita a ST no RN')
    if contains_any(name, ('AGUA MINERAL', 'AGUA COM GAS', 'AGUA INDAIA')):
        return ('22011000', '0300600', 'água mineral/potável sujeita a ST no RN')
    soda = (
        'COCA', 'PEPSI', 'GUARANA', 'FANTA', 'SPRITE', 'SUKITA', 'DORE ',
        'GRAPETTE', 'GUAPETTE', 'REFRI', 'REFRIGERANTE', 'SCHWEPPES',
        'CAJUINA', 'H2OH', 'AGUA TONICA', 'SODA LIMONADA',
    )
    if contains_any(name, soda):
        if 'LATA' in name or re.search(r'\b(250|290|350|473)\s?ML\b', name):
            cest = '0301002'
        elif re.search(r'\b(1|1 5|2)\s?L\b', name):
            cest = '0301001'
        else:
            cest = '0301100'
        return ('22021000', cest, 'refrigerante/água aromatizada sujeita a ST no RN')
    return None


def _specific_ncm(name, group, own):
    # Para itens preparados pela loja, classificar o produto final, e não um
    # ingrediente citado no nome (por exemplo, pão COM queijo ou manteiga).
    if own:
        if 'TAPIOCA' in name:
            return '19030000', 'tapioca preparada'
        if contains_any(name, ('SOPA', 'CANJA')):
            return '21041011', 'preparação para caldo/sopa'
        if contains_any(name, ('JANTA', 'BUFFET', 'SALADA', 'OVO MEXIDO',
                               'CAFE DA MANHA', 'CUSCUZ')):
            return '21069090', 'preparação alimentícia pronta'
        if group == 'COZINHA':
            return '21069090', 'preparação alimentícia de fabricação própria'
        if group in {'PADARIA', 'CONFEITARIA'}:
            if name.startswith(('CAFE ', 'SUCO ', 'ACHOCOLATADO', 'CHOCOLATE QUENTE')):
                return '22029900', 'bebida pronta não alcoólica'
            return '19059090', 'produto de padaria/confeitaria de fabricação própria'

    if group == 'PADARIA' and name.startswith(('PAO ', 'PÃO ')):
        return '19059090', 'produto de padaria industrializado'

    # Em produtos industrializados, a forma do produto prevalece sobre o
    # sabor/ingrediente mencionado na descrição ("salgadinho de queijo",
    # "biscoito de leite", "chocolate ao leite").
    if not own:
        if 'WAFER' in name or 'WEFER' in name:
            return '19053200', 'wafer'
        if 'BARRA DE CEREAL' in name:
            return '19042000', 'barra/preparação de cereal'
        if contains_any(name, ('FANDANGOS', 'PIPPO', 'CHEETOS', 'CHEETROS', 'DORITOS',
                               'TORCIDA ', 'KRO SABOR', 'CEBOLITOS', 'PIPOCA BOKUS',
                               'KI GALINHA', 'KI CHURRASCO', 'KI QUEIJO')):
            return '19041000', 'salgadinho/produto à base de cereal'
        if contains_any(name, ('CREME CRACKER', 'CREME CRACK ', 'TORRADINHA',
                               'SODA PRETA', 'SORDA PRETA', 'SODA BRANCA',
                               'MARAGOGI SALGADA', 'PETISCO DE ALHO',
                               'PETISCO DE CEBOLA', 'PETISCO DE CARNE DE SOL',
                               'PETISCO DE QUEIJO')):
            return '19059020', 'biscoito/petisco salgado'
        if contains_any(name, ('BISCOITO', 'BOLACHA', 'ROSQUINHA', 'SEQUILHO', 'TARECO',
                               'CASADINHA')):
            return '19053100', 'biscoito doce'
        if contains_any(name, ('KITKAT', 'BATON', 'CHOCOLATE', 'TRUFA', 'OVO DE COLHER')):
            return '18069000', 'chocolate/produto contendo cacau'
        if contains_any(name, ('CAPPUCCINO', 'CAFE COM LEITE')):
            return '21011200', 'preparação à base de café'

    # Higiene, limpeza e descartáveis.
    rules = (
        (('CREME DENTAL',), '33061000', 'dentifrício'),
        (('SABONETE',), '34011190', 'sabonete de toucador'),
        (('PAPEL HIGIENICO',), '48181000', 'papel higiênico'),
        (('GUARDANAPO',), '48183000', 'guardanapo de papel'),
        (('FOSFORO',), '36050000', 'fósforo'),
        (('ESPONJA DE ACO',), '73231000', 'esponja de aço'),
        (('ESPONJA', 'BUCHA DE LOUCA'), '39249000', 'esponja/artefato doméstico'),
        (('AGUA SANITARIA',), '28289011', 'água sanitária à base de hipoclorito'),
        (('DESINFETANTE',), '38089419', 'desinfetante'),
        (('DETERGENTE', 'MULTIUSO', 'LIMPA VIDRO', 'LIMPADOR', 'LAVA PISO',
          'LAVA ROUPA', 'TIXAN', 'CIF PERFUME', 'LIMPA CASA', 'ATOL COCO'),
         '34025000', 'preparação de limpeza acondicionada para venda a retalho'),
        (('COPO ', 'COLHER DESCARTAVEL', 'COLHER REFEICAO', 'COLHER SOBREMESA'),
         '39241000', 'artigo plástico de mesa/cozinha'),
        (('CANUDO',), '39173290', 'tubo/canudo de plástico'),
    )
    for terms, ncm, label in rules:
        if contains_any(name, terms):
            return ncm, label

    # Lácteos, ovos e gorduras.
    if contains_any(name, ('MARGARINA', 'DELINE ', 'CLAYBOM', 'PRIMOR ', 'DELICIA ')):
        return '15171000', 'margarina'
    if 'MANTEIGA' in name:
        return '04051000', 'manteiga'
    if name == 'NATA':
        return '04015021', 'creme de leite/nata'
    if contains_any(name, ('LEITE CONDENSADO', 'LEITE COND ')):
        return '04029900', 'leite condensado'
    if 'CREME DE LEITE' in name or 'CREME CULINARIO' in name:
        return '04015021', 'creme de leite UHT'
    if 'LEITE EM PO' in name:
        return '04022110', 'leite em pó integral'
    if contains_any(name, ('BEBIDA LACTEA', 'LEITE FERMENTADO', 'COALHADA', 'IOGURTE')):
        return '04039000', 'leite fermentado/coalhada'
    if re.search(r'\bLEITE\b', name) and not contains_any(name, ('NINHO', 'CONDENSADO')):
        return '04012010', 'leite UHT'
    if contains_any(name, ('REQUEIJAO', 'QUEIJO COALHO', 'QUEIJO MANTEIGA')):
        return '04061090', 'queijo fresco/requeijão'
    if 'MUSSARELA' in name:
        return '04061010', 'queijo muçarela'
    if 'QUEIJO' in name and not own:
        return '04069090', 'outro queijo'
    if re.search(r'\bOVO(S)?\b', name) and not own:
        return '04072100', 'ovo de galinha com casca'

    # Mercearia seca, conservas e condimentos.
    if contains_any(name, ('CAFE SOLUVEL', 'NESCAFE')):
        return '21011110', 'café solúvel'
    if contains_any(name, ('CAPPUCCINO', 'CAFE COM LEITE')) and not own:
        return '21011200', 'preparação à base de café'
    if re.search(r'\bCAFE\b', name) and not own:
        return '09012100', 'café torrado'
    if 'ACUCAR' in name:
        return '17019900', 'açúcar refinado/cristal'
    if re.search(r'\bSAL\b', name):
        return '25010020', 'sal de mesa'
    if contains_any(name, ('FLOCAO', 'FLOKAO', 'FORTE MILHO', 'FLOMIL', 'CUSCUZ GOSTOSIN')):
        return '11022000', 'farinha/fubá de milho'
    if contains_any(name, ('MAIZENA', 'CREMOGEMA')):
        return '11081200', 'amido de milho'
    if 'FARINHA DE MANDIOCA' in name:
        return '11062000', 'farinha de mandioca'
    if re.search(r'\bFARINHA\b', name):
        return '11010010', 'farinha de trigo'
    if contains_any(name, ('POLVILHO', 'GOMA ', 'TAPIOCA BANDEJA', 'TAPIOCA BANDEIJA',
                           'TAPIOCA CAICO')) and not own:
        return '11081400', 'fécula de mandioca'
    if contains_any(name, ('MILHO PIPOCA', 'MUNGUNZA')) and not own:
        return '10059010', 'milho em grão'
    if 'MILHO VERDE' in name or 'MILHO FUGINI' in name:
        return '20058000', 'milho doce preparado/conservado'
    if 'ERVILHA' in name:
        return '20054000', 'ervilha preparada/conservada'
    if 'DUETO FUGINI' in name:
        return '20059900', 'mistura de vegetais preparada/conservada'
    if contains_any(name, ('OLEO DE SOJA', 'OLEO SOYA', 'OLEO LIZA', 'OLEO ABC',
                           'OLEO CONCORDIA')):
        return '15079011', 'óleo de soja refinado'
    if contains_any(name, ('MIOJO', 'CUP NOODLES')):
        return '19023000', 'massa alimentícia preparada/instantânea'
    if contains_any(name, ('MACARRAO', 'MACARAO', 'ESPAGUETE')):
        return '19021900', 'massa alimentícia não cozida'
    if contains_any(name, ('MOLHO DE TOMATE', 'MOLHO TOMATE', 'MOLHO PRONTO',
                           'MOLHO QUERO', 'EXTRATO QUERO', 'KETCHUP', 'KATCHUP')):
        return '21032010', 'molho/extrato de tomate ou ketchup'
    if 'MAIONESE' in name:
        return '21039021', 'maionese'
    if contains_any(name, ('CALDO ', 'SAZON', 'TEMPERO', 'COLORIFERO')):
        return '21039029', 'tempero/condimento composto'
    if 'COLORIIFERO' in name:
        return '21039029', 'tempero/colorífico'
    if 'PASTA DE ALHO' in name:
        return '21039029', 'pasta/tempero de alho'
    if 'MASSA PARA PASTEL' in name:
        return '19012000', 'massa para produtos de padaria/pastel'
    if contains_any(name, ('REFRESCO FRISCO', 'RFRESCO FRISCO', 'FRISCO MORANGO',
                           'SUCO EM PO', 'SUCO LIMAO EM PO')):
        return '21069010', 'preparação em pó para bebida'
    if 'VINAGRE' in name:
        return '22090000', 'vinagre'
    if 'SARDINHA' in name:
        return '16041310', 'sardinha em conserva'
    if contains_any(name, ('SALSICHA', 'MORTADELA', 'MORT ', 'LOMBINHO')):
        return '16010000', 'embutido de carne'
    if 'PRESUNTO' in name and not own:
        return '16024100', 'presunto suíno preparado'
    if 'PEITO DE PERU' in name:
        return '16023230', 'preparação de peru'
    if 'FIAMBRE' in name:
        return '16024900', 'preparação de carne suína'
    if 'PATE' in name and not own:
        return '16022000', 'preparação/patê de fígado ou carne'

    # Bomboniere, biscoitos, salgadinhos e panificação.
    if contains_any(name, ('TRIDENT', 'BIGBIG', 'BLONG', 'CHICLETE')):
        return '17041000', 'goma de mascar'
    if contains_any(name, ('FINI ', 'JUJUBA', 'BALA ', 'BALAS ', 'DROPS', 'HALLS',
                           'FREEGELLS', 'PIRULITO', 'CARAMELO')):
        return '17049020', 'produto de confeitaria sem cacau'
    if contains_any(name, ('BARRA DE CEREAL',)):
        return '19042000', 'barra/preparação de cereal'
    if 'WAFER' in name or 'WEFER' in name:
        return '19053200', 'wafer'
    if contains_any(name, ('KITKAT', 'BATON', 'CHOCOLATE', 'TRUFA', 'OVO DE COLHER')) and not own:
        return '18069000', 'chocolate/produto contendo cacau'
    if contains_any(name, ('CREME CRACKER', 'CREME CRACK ', 'TORRADINHA')) and not own:
        return '19059020', 'biscoito salgado'
    if contains_any(name, ('BISCOITO', 'BOLACHA', 'ROSQUINHA', 'SEQUILHO', 'TARECO',
                           'CASADINHA')) and not own:
        return '19053100', 'biscoito doce'
    if contains_any(name, ('RUFFLES', 'BATATA SENSACAO', 'BATATA PALHA')):
        return '20052000', 'batata preparada/conservada'
    if contains_any(name, ('FANDANGOS', 'PIPPO', 'CHEETOS', 'CHEETROS', 'DORITOS',
                           'TORCIDA ', 'KRO SABOR', 'CEBOLITOS', 'PIPOCA BOKUS',
                           'KI GALINHA', 'KI CHURRASCO', 'KI QUEIJO')):
        return '19041000', 'salgadinho/produto à base de cereal'
    if contains_any(name, ('PAÇOCA', 'PACOCA', 'PACOQUINHA', 'PE DE MULEQUE', 'RAPADURA')):
        return '17049090', 'doce/confeito sem cacau'
    if contains_any(name, ('PAO DE FORMA', 'PAO FORMA', 'PAO BISNAGUINHA', 'PANETONE',
                           'CHOCOTONE', 'BAURU')) and not own:
        return '19059090', 'produto de padaria industrializado'
    if contains_any(name, ('BOLO DE ROLO', 'ROCAMBOLE', 'RAIVINHA CASEIRA',
                           'BOLINHOS AMIDULAR')) and not own:
        return '19059090', 'produto de padaria/confeitaria industrializado'
    if name == 'TRELOSO':
        return '19053100', 'biscoito doce'
    if contains_any(name, ('DELICIT CRISTAL', 'FOLHEADA DO SERTAO')):
        return '19053100', 'biscoito doce'
    if contains_any(name, ('SODA PRETA', 'SORDA PRETA', 'SODA BRANCA', 'MARAGOGI SALGADA',
                           'PETISCO DE ALHO', 'PETISCO DE CEBOLA',
                           'PETISCO DE CARNE DE SOL')):
        return '19059020', 'biscoito/petisco salgado'
    if contains_any(name, ('PAO DE LO', 'CANUDINHO', 'NEGA MALUCA FATIA',
                           'MINI EMPADA DOCE')):
        return '19059090', 'produto de padaria/confeitaria'
    if 'BOKUS DOCE' in name:
        return '19041000', 'pipoca/produto à base de cereal'
    if 'BEIJU' in name:
        return '19030000', 'tapioca/beiju preparado'
    if contains_any(name, ('TAPIOCA BANDEJA', 'TAPIOCA BANDEIJA')):
        return '11081400', 'fécula/goma de mandioca'
    if 'SUSPIRO' in name:
        return '17049090', 'suspiro/doce sem cacau'
    if 'ITACOLOMY' in name:
        return '04061090', 'requeijão/queijo fresco'
    if 'SORV SUNDAE' in name:
        return '21050010', 'sorvete'
    if contains_any(name, ('ACHOCOLATADO',)):
        return '18069000', 'preparação contendo cacau'
    if contains_any(name, ('CHA VERDE',)):
        return '09021000', 'chá verde'
    if name.startswith('CHA '):
        return '12119090', 'erva/planta para infusão'

    # Preparações e bebidas prontas.
    if own and 'TAPIOCA' in name:
        return '19030000', 'tapioca preparada'
    if own and contains_any(name, ('SOPA', 'CANJA')):
        return '21041011', 'preparação para caldo/sopa'
    if own and contains_any(name, ('JANTA', 'BUFFET', 'SALADA', 'OVO MEXIDO',
                                   'CAFE DA MANHA', 'CUSCUZ')):
        return '21069090', 'preparação alimentícia pronta'
    if own and contains_any(name, ('CAFE ', 'CAPPUCCINO', 'CHOCOLATE QUENTE', 'SUCO')):
        return '22029900', 'bebida pronta não alcoólica'
    if contains_any(name, ('SUCO', 'REFRESCO', 'TAMPICO', 'KAPO', 'DELVALLE',
                           'DEL VALLE', 'DAFRUTA', 'D FRUTA', 'FRUIT SHOOT',
                           'MARATA SABOR', 'SUMO ', 'BEBIDA DE FRUTA', 'NESCAU',
                           'TODDYNHO', 'NESQUIK', 'ICE TEA', 'ITALAKINHO',
                           'DAMARE KIDS', 'DAMARE CHOCO')):
        return '22029900', 'suco/néctar/refresco pronto'
    if group == 'BEBIDA' and name.startswith('D '):
        return '22029900', 'bebida/refresco pronto'
    if 'AQUACOCO' in name:
        return '20098990', 'água/suco de coco'
    if contains_any(name, ('SABAO BARRA', 'SABAO YPE')):
        return '34011900', 'sabão em barra'
    if contains_any(name, ('PAPEL SUBLIME', 'YPE PERFUMES')):
        return ('48181000', 'papel higiênico') if 'PAPEL' in name else (
            '34025000', 'preparação de limpeza'
        )
    if name in {'B1 100 UNI', 'B2 100 UNI', 'H1 100 UNI', 'H2 100 UNI'}:
        return '39241000', 'recipiente/artigo plástico descartável'
    if 'CHANTILLY' in name:
        return '19019090', 'preparação alimentícia à base de leite'

    if own and group in {'PADARIA', 'CONFEITARIA'}:
        return '19059090', 'produto de padaria/confeitaria de fabricação própria'
    if own and group == 'COZINHA':
        return '21069090', 'preparação alimentícia de fabricação própria'
    if group == 'PADARIA' and 'PAO ' in name:
        return '19059090', 'produto de padaria'
    if group == 'DIVERSOS' and name == 'PAO':
        return '19059090', 'produto de padaria'
    return None


def suggest_fiscal_fields(product):
    name = normalize(product.nome)
    group = normalize(product.grupo)
    own = _is_own_production(product, name, group)
    st = _beverage_st(name, group) if not own else None
    specific = _specific_ncm(name, group, own)

    if st:
        ncm, cest, rationale = st
        cfop, csosn = '5405', '500'
        confidence = Produto.ConfiancaFiscal.MEDIA
    else:
        cest = ''
        cfop, csosn = ('5101', '102') if own else ('5102', '102')
        if specific:
            ncm, rationale = specific
            confidence = Produto.ConfiancaFiscal.MEDIA
        else:
            fallback = {
                'PADARIA': ('19059090', 'produto de padaria'),
                'CONFEITARIA': ('19059090', 'produto de confeitaria'),
                'COZINHA': ('21069090', 'preparação alimentícia'),
                'BEBIDA': ('22029900', 'outra bebida não alcoólica'),
                'BOMBONIERE': ('17049090', 'outro produto de confeitaria'),
                'LATICINIOS': ('04069090', 'outro produto lácteo/queijo'),
                'GOMA': ('11081400', 'fécula de mandioca'),
                'HIGIENE': ('34025000', 'preparação de limpeza'),
                'CEREAIS': ('21069090', 'outra preparação alimentícia'),
                'CONVENIENCIA': ('21069090', 'outra preparação alimentícia'),
                'DIVERSOS': ('21069090', 'outra preparação alimentícia'),
            }
            ncm, rationale = fallback.get(group, ('21069090', 'outra preparação alimentícia'))
            confidence = Produto.ConfiancaFiscal.BAIXA

    barcode = re.sub(r'\D', '', product.codigo_barras or '')
    gtin = barcode if not own and gtin_valido(barcode) else ''
    commercial_origin = (
        Produto.TipoOrigemComercial.FABRICACAO_PROPRIA
        if own else Produto.TipoOrigemComercial.REVENDA
    )
    sources = f'{RFB_NCM_SOURCE}; {SPED_SOURCE}'
    if st:
        sources += f'; {RN_ST_SOURCE}'
    observation = (
        f'Classificação automatizada por família: {rationale}. '
        f'{"Validar ficha técnica" if own else "Conferir com XML de compra"}.'
    )
    if confidence == Produto.ConfiancaFiscal.BAIXA:
        observation += ' NCM provisório por ausência de descrição suficiente no cadastro.'

    return {
        'ncm': ncm,
        'cest': cest,
        'cfop': cfop,
        'cst_icms': csosn,
        'cst_pis': '49',
        'cst_cofins': '49',
        'origem_mercadoria': '0',
        'codigo_beneficio_fiscal': '',
        'unidade_tributavel': (product.unidade_medida or 'UN').upper()[:6],
        'gtin_tributavel': gtin,
        'fator_conversao_tributavel': '1',
        'aliquota_icms': '0',
        'aliquota_pis': '0',
        'aliquota_cofins': '0',
        'tipo_origem_comercial': commercial_origin,
        'fiscal_confianca': confidence,
        'fiscal_fonte': sources,
        'fiscal_observacao': observation,
    }
