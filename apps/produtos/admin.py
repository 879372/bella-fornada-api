
from django.contrib import admin

from .models import ItemRevisaoFiscal, LoteRevisaoFiscal, Produto


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo_legado', 'nome', 'tipo_origem_comercial', 'ncm', 'cfop',
        'cst_icms', 'fiscal_confianca', 'ativo',
    )
    search_fields = ('nome', 'codigo_legado', 'codigo_barras', 'ncm')
    list_filter = ('tipo_origem_comercial', 'fiscal_confianca', 'ativo')
    readonly_fields = (
        'ncm', 'cest', 'cfop', 'cst_icms', 'cst_pis', 'cst_cofins',
        'origem_mercadoria', 'codigo_beneficio_fiscal',
        'unidade_tributavel', 'gtin_tributavel',
        'fator_conversao_tributavel', 'aliquota_icms', 'aliquota_pis',
        'aliquota_cofins', 'tipo_origem_comercial', 'fiscal_confianca',
        'fiscal_fonte', 'fiscal_observacao', 'fiscal_revisado_em',
    )


class ItemRevisaoFiscalInline(admin.TabularInline):
    model = ItemRevisaoFiscal
    extra = 0
    can_delete = False
    readonly_fields = ('produto', 'codigo_legado', 'nome', 'antes', 'depois')


@admin.register(LoteRevisaoFiscal)
class LoteRevisaoFiscalAdmin(admin.ModelAdmin):
    list_display = ('id_externo', 'status', 'created_at', 'revertido_em')
    readonly_fields = (
        'id_externo', 'status', 'catalogo_checksum', 'mapeamento_checksum',
        'fonte', 'observacao', 'created_at', 'updated_at', 'revertido_em',
    )
    inlines = (ItemRevisaoFiscalInline,)
