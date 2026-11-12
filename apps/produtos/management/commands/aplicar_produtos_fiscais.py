import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.produtos.fiscal_review import (
    catalog_checksum,
    coerce_fiscal_fields,
    fiscal_snapshot,
    mapping_checksum,
    validate_fiscal_fields,
)
from apps.produtos.models import ItemRevisaoFiscal, LoteRevisaoFiscal, Produto


class Command(BaseCommand):
    help = 'Simula/aplica um mapeamento fiscal auditável ou reverte um lote.'

    def add_arguments(self, parser):
        parser.add_argument('arquivo', nargs='?')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--rollback')

    def handle(self, *args, **options):
        if options['rollback']:
            if options['arquivo']:
                raise CommandError('Não informe arquivo junto com --rollback.')
            return self._rollback(options['rollback'], apply=options['apply'])
        if not options['arquivo']:
            raise CommandError('Informe o arquivo JSON de mapeamento.')

        path = Path(options['arquivo'])
        if not path.is_file():
            raise CommandError(f'Arquivo não encontrado: {path}')
        try:
            mapping = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'Mapeamento inválido: {exc}') from exc
        return self._apply_mapping(mapping, apply=options['apply'])

    def _apply_mapping(self, mapping, *, apply):
        if mapping.get('versao') != 1 or not isinstance(mapping.get('produtos'), list):
            raise CommandError('O mapeamento deve usar versao=1 e conter a lista produtos.')

        expected_catalog = mapping.get('catalogo_checksum')
        current_catalog = catalog_checksum()
        if apply and not expected_catalog:
            raise CommandError(
                'A aplicação exige catalogo_checksum; execute primeiro a simulação/auditoria.'
            )
        if expected_catalog and expected_catalog != current_catalog:
            raise CommandError(
                'O catálogo mudou desde a auditoria. Gere um novo checksum antes de aplicar.'
            )

        prepared = []
        seen = set()
        for row_number, entry in enumerate(mapping['produtos'], start=1):
            try:
                legacy_code = int(entry.get('codigo_legado'))
            except (TypeError, ValueError) as exc:
                raise CommandError(
                    f'Linha {row_number}: código legado deve ser um número inteiro.'
                ) from exc
            expected_name = str(entry.get('nome') or '').strip()
            if legacy_code <= 0 or not expected_name or not isinstance(entry.get('campos'), dict):
                raise CommandError(f'Linha {row_number}: código, nome e campos são obrigatórios.')
            if legacy_code in seen:
                raise CommandError(f'Código legado duplicado no mapeamento: {legacy_code}.')
            seen.add(legacy_code)
            try:
                product = Produto.all_objects.get(codigo_legado=legacy_code)
            except Produto.DoesNotExist as exc:
                raise CommandError(f'Produto legado {legacy_code} não encontrado.') from exc
            if product.nome.strip() != expected_name:
                raise CommandError(
                    f'Produto {legacy_code} mudou de nome: esperado {expected_name!r}, '
                    f'atual {product.nome!r}.'
                )
            try:
                changes = coerce_fiscal_fields(entry['campos'])
                normalized = validate_fiscal_fields(product, changes)
            except ValidationError as exc:
                details = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
                raise CommandError(f'Produto {legacy_code}: {details}') from exc
            effective = {
                field: normalized[field]
                for field in changes
                if getattr(product, field) != normalized[field]
            }
            if effective:
                prepared.append((
                    product,
                    effective,
                    fiscal_snapshot(product, fields=effective.keys()),
                ))

        report = {
            'modo': 'APLICACAO' if apply else 'SIMULACAO',
            'catalogo_checksum': current_catalog,
            'mapeamento_checksum': mapping_checksum(mapping),
            'produtos_no_arquivo': len(mapping['produtos']),
            'produtos_com_alteracao': len(prepared),
            'codigos_alterados': [product.codigo_legado for product, _, _ in prepared],
        }
        if not apply:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        if not prepared:
            report['lote'] = None
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        with transaction.atomic():
            locked = {
                product.codigo_legado: product
                for product in Produto.all_objects.select_for_update().filter(
                    codigo_legado__in=[product.codigo_legado for product, _, _ in prepared]
                )
            }
            if len(locked) != len(prepared):
                raise CommandError('O catálogo mudou durante a aplicação; operação abortada.')
            lote = LoteRevisaoFiscal.objects.create(
                status=LoteRevisaoFiscal.Status.APLICADO,
                catalogo_checksum=current_catalog,
                mapeamento_checksum=report['mapeamento_checksum'],
                fonte=str(mapping.get('fonte') or ''),
                observacao=str(mapping.get('observacao') or ''),
            )
            now = timezone.now()
            for original, changes, expected_before in prepared:
                product = locked[original.codigo_legado]
                if (
                    product.nome.strip() != original.nome.strip()
                    or product.updated_at != original.updated_at
                    or fiscal_snapshot(product, fields=changes.keys()) != expected_before
                ):
                    raise CommandError(f'Produto {product.codigo_legado} mudou durante a aplicação.')
                before = fiscal_snapshot(product, fields=changes.keys())
                for field, value in changes.items():
                    setattr(product, field, value)
                product.fiscal_revisado_em = now
                product.save(update_fields=[*changes.keys(), 'fiscal_revisado_em', 'updated_at'])
                after = fiscal_snapshot(product, fields=changes.keys())
                ItemRevisaoFiscal.objects.create(
                    lote=lote,
                    produto=product,
                    codigo_legado=product.codigo_legado,
                    nome=product.nome,
                    antes=before,
                    depois=after,
                )
            report['lote'] = str(lote.id_externo)
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))

    def _rollback(self, batch_external_id, *, apply):
        try:
            batch = LoteRevisaoFiscal.all_objects.get(id_externo=batch_external_id)
        except (LoteRevisaoFiscal.DoesNotExist, ValidationError) as exc:
            raise CommandError('Lote fiscal não encontrado.') from exc
        if batch.status != LoteRevisaoFiscal.Status.APLICADO:
            raise CommandError('Somente lotes aplicados podem ser revertidos.')

        items = list(batch.itens.select_related('produto').order_by('codigo_legado'))
        report = {
            'modo': 'ROLLBACK' if apply else 'SIMULACAO_ROLLBACK',
            'lote': str(batch.id_externo),
            'produtos': len(items),
            'codigos': [item.codigo_legado for item in items],
        }
        if not apply:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        with transaction.atomic():
            locked = {
                product.pk: product
                for product in Produto.all_objects.select_for_update().filter(
                    pk__in=[item.produto_id for item in items]
                )
            }
            for item in items:
                product = locked[item.produto_id]
                current = fiscal_snapshot(product, fields=item.depois.keys())
                if current != item.depois:
                    raise CommandError(
                        f'Produto {item.codigo_legado} foi alterado após o lote; rollback abortado.'
                    )
            now = timezone.now()
            for item in items:
                product = locked[item.produto_id]
                restored = coerce_fiscal_fields(item.antes)
                for field, value in restored.items():
                    setattr(product, field, value)
                product.fiscal_revisado_em = now
                product.save(update_fields=[*restored.keys(), 'fiscal_revisado_em', 'updated_at'])
            batch.status = LoteRevisaoFiscal.Status.REVERTIDO
            batch.revertido_em = now
            batch.save(update_fields=['status', 'revertido_em', 'updated_at'])
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
