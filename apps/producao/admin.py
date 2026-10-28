from django.contrib import admin

from .models import OrdemProducao, PerdaProducao, Receita, ReceitaIngrediente


class ReceitaIngredienteInline(admin.TabularInline):
    model = ReceitaIngrediente
    extra = 1


@admin.register(Receita)
class ReceitaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'produto', 'rendimento', 'unidade_rendimento', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome', 'produto__nome')
    inlines = (ReceitaIngredienteInline,)


@admin.register(OrdemProducao)
class OrdemProducaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'receita', 'quantidade_lotes', 'status', 'data_planejada')
    list_filter = ('status',)
    search_fields = ('receita__nome', 'codigo_lote')


@admin.register(PerdaProducao)
class PerdaProducaoAdmin(admin.ModelAdmin):
    list_display = ('produto', 'quantidade', 'motivo', 'created_at')
    list_filter = ('motivo',)

