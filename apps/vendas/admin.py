from django.contrib import admin

from .models import OperacaoCaixa, SessaoCaixa, Venda, VendaItem, VendaPagamento


class VendaItemInline(admin.TabularInline):
    model = VendaItem
    extra = 0
    raw_id_fields = ('produto',)


class VendaPagamentoInline(admin.TabularInline):
    model = VendaPagamento
    extra = 0


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ('id', 'data', 'canal', 'status', 'cliente', 'total')
    list_filter = ('status', 'canal')
    search_fields = ('id', 'id_externo', 'cliente__nome')
    raw_id_fields = ('sessao', 'cliente', 'cancelada_por')
    inlines = (VendaItemInline, VendaPagamentoInline)


class OperacaoCaixaInline(admin.TabularInline):
    model = OperacaoCaixa
    extra = 0


@admin.register(SessaoCaixa)
class SessaoCaixaAdmin(admin.ModelAdmin):
    list_display = ('id', 'operador', 'status', 'data_abertura', 'data_fechamento', 'fundo_inicial')
    list_filter = ('status',)
    inlines = (OperacaoCaixaInline,)
