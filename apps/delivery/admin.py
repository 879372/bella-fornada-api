from django.contrib import admin

from .models import (
    BairroEntrega,
    Complemento,
    ConfiguracaoDelivery,
    Entregador,
    GrupoComplemento,
    HistoricoPedido,
    PedidoDelivery,
    PedidoItem,
    PedidoItemComplemento,
    ProdutoGrupoComplemento,
)


@admin.register(ConfiguracaoDelivery)
class ConfiguracaoDeliveryAdmin(admin.ModelAdmin):
    list_display = ("nome_loja", "slug", "aceita_pedidos", "updated_at")
    prepopulated_fields = {"slug": ("nome_loja",)}


@admin.register(BairroEntrega)
class BairroEntregaAdmin(admin.ModelAdmin):
    list_display = ("nome", "taxa_entrega", "ativo", "ordem")
    list_filter = ("ativo",)
    search_fields = ("nome",)


class ComplementoInline(admin.TabularInline):
    model = Complemento
    extra = 0


@admin.register(GrupoComplemento)
class GrupoComplementoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "ordem")
    list_filter = ("ativo",)
    inlines = (ComplementoInline,)


@admin.register(Complemento)
class ComplementoAdmin(admin.ModelAdmin):
    list_display = ("nome", "grupo", "preco_adicional", "ativo", "ordem")
    list_filter = ("ativo", "grupo")
    search_fields = ("nome", "grupo__nome")


@admin.register(ProdutoGrupoComplemento)
class ProdutoGrupoComplementoAdmin(admin.ModelAdmin):
    list_display = (
        "produto",
        "grupo",
        "minimo_escolhas",
        "maximo_escolhas",
        "ordem",
    )
    search_fields = ("produto__nome", "grupo__nome")


@admin.register(Entregador)
class EntregadorAdmin(admin.ModelAdmin):
    list_display = ("nome", "telefone", "usuario", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "telefone")


class PedidoItemComplementoInline(admin.TabularInline):
    model = PedidoItemComplemento
    extra = 0
    readonly_fields = ("complemento", "grupo_nome", "complemento_nome", "preco_adicional")
    can_delete = False


@admin.register(PedidoItem)
class PedidoItemAdmin(admin.ModelAdmin):
    list_display = ("pedido", "produto_nome", "quantidade", "preco_unitario", "subtotal")
    readonly_fields = (
        "pedido",
        "produto",
        "produto_nome",
        "unidade_medida",
        "preco_base_unitario",
        "preco_complementos_unitario",
        "preco_unitario",
        "quantidade",
        "subtotal",
        "observacoes",
        "created_at",
    )
    inlines = (PedidoItemComplementoInline,)


class HistoricoPedidoInline(admin.TabularInline):
    model = HistoricoPedido
    extra = 0
    readonly_fields = (
        "tipo",
        "status_anterior",
        "status_novo",
        "observacao",
        "alterado_por",
        "created_at",
    )
    can_delete = False


@admin.register(PedidoDelivery)
class PedidoDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nome_cliente",
        "status",
        "fulfillment",
        "payment_method",
        "total",
        "entregador",
        "created_at",
    )
    list_filter = ("status", "fulfillment", "payment_method", "pagamento_confirmado")
    search_fields = ("nome_cliente", "telefone_cliente", "rastreamento_token")
    readonly_fields = (
        "rastreamento_token",
        "idempotency_key",
        "request_fingerprint",
        "subtotal",
        "taxa_entrega",
        "total",
        "venda",
        "created_at",
        "updated_at",
    )
    inlines = (HistoricoPedidoInline,)


@admin.register(HistoricoPedido)
class HistoricoPedidoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "tipo", "status_anterior", "status_novo", "alterado_por", "created_at")
    list_filter = ("tipo", "status_novo")
    readonly_fields = (
        "pedido",
        "tipo",
        "status_anterior",
        "status_novo",
        "observacao",
        "alterado_por",
        "created_at",
    )
