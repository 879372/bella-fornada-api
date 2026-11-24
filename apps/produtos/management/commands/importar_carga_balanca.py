from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.produtos.balanca_mgv import ErroCargaBalanca, ler_itensmgv
from apps.produtos.models import Produto


class Command(BaseCommand):
    help = (
        'Lê o ITENSMGV.TXT do sistema legado e marca no cadastro quais produtos vão '
        'para a balança, com tipo e validade. Use --atualizar-precos para aplicar '
        'os preços do TXT. O nome não é alterado.'
    )

    def add_arguments(self, parser):
        parser.add_argument('arquivo', type=Path)
        parser.add_argument(
            '--substituir', action='store_true',
            help='Desmarca da balança os produtos que não estão no arquivo.',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--atualizar-precos', action='store_true',
                            help='Atualiza o preço de venda usando o valor do TXT.')

    def handle(self, arquivo, substituir, dry_run, atualizar_precos, **options):
        try:
            itens = ler_itensmgv(arquivo.read_bytes())
        except (OSError, ErroCargaBalanca) as exc:
            raise CommandError(str(exc)) from exc

        produtos = {
            p.codigo_legado: p
            for p in Produto.objects.filter(codigo_legado__in=[i.codigo for i in itens])
        }
        faltando, precos, nomes, atualizar = [], [], [], []
        for item in itens:
            produto = produtos.get(item.codigo)
            if produto is None:
                faltando.append(item)
                continue
            if produto.preco_venda != item.preco:
                precos.append((item, produto.preco_venda))
            if produto.nome.strip().upper() != item.descritivo.strip().upper():
                nomes.append((item, produto.nome))
            produto.enviar_balanca = True
            produto.tipo_balanca = item.tipo
            produto.validade_balanca_dias = item.validade_dias
            if atualizar_precos:
                produto.preco_venda = item.preco
            produto.updated_at = timezone.now()
            atualizar.append(produto)

        with transaction.atomic():
            desmarcados = 0
            if substituir:
                desmarcados = Produto.objects.filter(enviar_balanca=True).exclude(
                    codigo_legado__in=list(produtos)
                ).update(enviar_balanca=False)
            campos = ['enviar_balanca', 'tipo_balanca', 'validade_balanca_dias', 'updated_at']
            if atualizar_precos:
                campos.append('preco_venda')
            Produto.objects.bulk_update(atualizar, campos)
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(f'Itens no arquivo: {len(itens)}')
        self.stdout.write(self.style.SUCCESS(f'Produtos marcados para a balança: {len(atualizar)}'))
        if substituir:
            self.stdout.write(f'Produtos desmarcados: {desmarcados}')
        if atualizar_precos:
            self.stdout.write(f'Preços atualizados pelo TXT: {len(precos)}')
        for item in faltando:
            self.stdout.write(self.style.WARNING(
                f'Sem cadastro: código {item.codigo} - {item.descritivo}'
            ))
        for item, nome_atual in nomes:
            self.stdout.write(self.style.WARNING(
                f'Nome diferente: {item.codigo} (TXT {item.descritivo.strip()}, '
                f'cadastro {nome_atual}). O nome foi preservado.'
            ))
        for item, preco_atual in precos:
            self.stdout.write(
                f'Preço diferente: {item.codigo} - {item.descritivo.strip()} '
                f'(legado {item.preco:.2f}, sistema {preco_atual:.2f})'
            )
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry-run: nada foi gravado.'))
