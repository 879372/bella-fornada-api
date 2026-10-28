from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.financeiro.models import ContaPagar, ContaReceber

class Command(BaseCommand):
    help = 'Atualiza o status de Contas a Pagar e Receber para VENCIDO se a data de vencimento passou'

    def handle(self, *args, **options):
        hoje = timezone.now().date()

        # Atualiza Contas a Pagar
        pagar_atualizadas = ContaPagar.objects.filter(
            status='PENDENTE',
            vencimento__lt=hoje
        ).update(status='VENCIDO')

        # Atualiza Contas a Receber
        receber_atualizadas = ContaReceber.objects.filter(
            status='PENDENTE',
            vencimento__lt=hoje
        ).update(status='VENCIDO')

        self.stdout.write(self.style.SUCCESS(
            f'Status atualizado com sucesso! {pagar_atualizadas} Contas a Pagar e {receber_atualizadas} Contas a Receber vencidas.'
        ))
