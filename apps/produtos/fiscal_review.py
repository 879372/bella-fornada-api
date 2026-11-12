import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from .barcodes import gtin_valido
from .fiscal_codes import NORMAL_ICMS_CST, PIS_COFINS_CST, SIMPLES_CSOSN
from .models import Produto


FISCAL_FIELDS = (
    'ncm', 'cest', 'cfop', 'cst_icms', 'cst_pis', 'cst_cofins',
    'origem_mercadoria', 'codigo_beneficio_fiscal',
    'unidade_tributavel', 'gtin_tributavel',
    'fator_conversao_tributavel', 'aliquota_icms', 'aliquota_pis',
    'aliquota_cofins', 'tipo_origem_comercial', 'fiscal_confianca',
    'fiscal_fonte', 'fiscal_observacao',
)

DECIMAL_FIELDS = {
    'fator_conversao_tributavel', 'aliquota_icms', 'aliquota_pis',
    'aliquota_cofins',
}


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def mapping_checksum(mapping):
    return hashlib.sha256(_canonical_json(mapping).encode()).hexdigest()


def catalog_checksum():
    digest = hashlib.sha256()
    rows = Produto.all_objects.order_by('codigo_legado', 'pk').values_list(
        'id_externo', 'codigo_legado', 'nome', 'updated_at',
    )
    for external_id, legacy_code, name, updated_at in rows.iterator():
        digest.update(_canonical_json([
            str(external_id), legacy_code, name, updated_at.isoformat(),
        ]).encode())
        digest.update(b'\n')
    return digest.hexdigest()


def fiscal_snapshot(product, fields=FISCAL_FIELDS):
    snapshot = {}
    for field in fields:
        value = getattr(product, field)
        # O PostgreSQL devolve Decimal com a escala do campo (por exemplo,
        # 1.000000), enquanto o JSON de entrada pode conter apenas 1. Usar uma
        # representação canônica evita falsos conflitos no rollback.
        snapshot[field] = (
            format(value.normalize(), 'f') if isinstance(value, Decimal) else value
        )
    return snapshot


def coerce_fiscal_fields(fields):
    unknown = sorted(set(fields) - set(FISCAL_FIELDS))
    if unknown:
        raise ValidationError(f'Campos fiscais não permitidos: {", ".join(unknown)}.')

    result = {}
    for field, value in fields.items():
        if field in DECIMAL_FIELDS:
            try:
                value = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError({field: 'Informe um número decimal válido.'}) from exc
            if not value.is_finite():
                raise ValidationError({field: 'Informe um número decimal finito.'})
        elif value is None:
            value = ''
        elif field not in {'tipo_origem_comercial', 'fiscal_confianca'}:
            value = str(value).strip()
        result[field] = value
    return result


def validate_fiscal_fields(current, changes):
    data = {field: getattr(current, field) for field in FISCAL_FIELDS}
    data.update(changes)

    errors = {}

    def digits(value):
        return ''.join(
            character for character in str(value or '') if character.isdigit()
        )

    ncm = digits(data['ncm'])
    if ncm and (len(ncm) != 8 or ncm == '00000000'):
        errors['ncm'] = 'NCM deve conter 8 dígitos e não pode ser 00000000.'
    data['ncm'] = ncm

    cest = digits(data['cest'])
    if cest and len(cest) != 7:
        errors['cest'] = 'CEST deve conter 7 dígitos.'
    data['cest'] = cest

    cfop = digits(data['cfop'])
    if len(cfop) != 4 or cfop[0] not in set('123567'):
        errors['cfop'] = 'CFOP deve conter 4 dígitos.'
    data['cfop'] = cfop

    cst_icms = digits(data['cst_icms'])
    if cst_icms not in SIMPLES_CSOSN | NORMAL_ICMS_CST:
        errors['cst_icms'] = 'CST/CSOSN não pertence ao conjunto válido.'
    data['cst_icms'] = cst_icms

    for field in ('cst_pis', 'cst_cofins'):
        cst = digits(data[field])
        if cst and cst not in PIS_COFINS_CST:
            errors[field] = 'CST de PIS/COFINS inválido.'
        data[field] = cst

    origem = digits(data['origem_mercadoria'])
    if origem not in set('012345678'):
        errors['origem_mercadoria'] = 'Origem da mercadoria deve estar entre 0 e 8.'
    data['origem_mercadoria'] = origem

    gtin = digits(data['gtin_tributavel'])
    if gtin and not gtin_valido(gtin):
        errors['gtin_tributavel'] = 'GTIN inválido ou código interno/variável.'
    data['gtin_tributavel'] = gtin

    data['unidade_tributavel'] = str(data['unidade_tributavel'] or '').upper()[:6]
    fator = Decimal(data['fator_conversao_tributavel'] or 0)
    if not fator.is_finite() or fator <= 0 or fator > Decimal('999999999.999999'):
        errors['fator_conversao_tributavel'] = 'O fator deve ser maior que zero.'

    for field in ('aliquota_icms', 'aliquota_pis', 'aliquota_cofins'):
        aliquota = Decimal(data[field] or 0)
        if not aliquota.is_finite() or not Decimal('0') <= aliquota <= Decimal('100'):
            errors[field] = 'A alíquota deve estar entre 0 e 100.'

    valid_types = {choice for choice, _ in Produto.TipoOrigemComercial.choices}
    if data['tipo_origem_comercial'] not in valid_types:
        errors['tipo_origem_comercial'] = 'Tipo de origem comercial inválido.'

    valid_confidence = {choice for choice, _ in Produto.ConfiancaFiscal.choices}
    if data['fiscal_confianca'] not in valid_confidence:
        errors['fiscal_confianca'] = 'Nível de confiança fiscal inválido.'
    if data['fiscal_confianca'] in {
        Produto.ConfiancaFiscal.ALTA, Produto.ConfiancaFiscal.MEDIA,
    } and not str(data['fiscal_fonte'] or '').strip():
        errors['fiscal_fonte'] = 'Informe a fonte para revisões de confiança alta ou média.'
    if data['fiscal_confianca'] == Produto.ConfiancaFiscal.ALTA and not ncm:
        errors['ncm'] = 'Revisão de confiança alta exige NCM.'
    if data['fiscal_confianca'] == Produto.ConfiancaFiscal.ALTA:
        if not data['cst_pis']:
            errors['cst_pis'] = 'Revisão de confiança alta exige CST PIS.'
        if not data['cst_cofins']:
            errors['cst_cofins'] = 'Revisão de confiança alta exige CST COFINS.'
        if data['tipo_origem_comercial'] == Produto.TipoOrigemComercial.NAO_CLASSIFICADO:
            errors['tipo_origem_comercial'] = (
                'Revisão de confiança alta exige a origem comercial do produto.'
            )
        if not data['unidade_tributavel']:
            errors['unidade_tributavel'] = (
                'Revisão de confiança alta exige unidade tributável.'
            )

    if errors:
        raise ValidationError(errors)
    return data
