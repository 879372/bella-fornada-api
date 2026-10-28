from django.contrib import admin

from .models import DocumentoFiscal, EventoFiscal, TentativaFiscal


class TentativaFiscalInline(admin.TabularInline):
    model = TentativaFiscal
    extra = 0
    can_delete = False
    fields = (
        "operacao",
        "resultado",
        "http_status",
        "status_remoto",
        "codigo_erro",
        "mensagem",
        "iniciada_em",
        "finalizada_em",
    )
    readonly_fields = fields


class EventoFiscalInline(admin.TabularInline):
    model = EventoFiscal
    extra = 0
    can_delete = False
    fields = (
        "tipo",
        "status_anterior",
        "status_novo",
        "descricao",
        "criado_em",
    )
    readonly_fields = fields


@admin.register(DocumentoFiscal)
class DocumentoFiscalAdmin(admin.ModelAdmin):
    list_display = (
        "referencia",
        "tipo",
        "status",
        "ambiente",
        "venda",
        "numero",
        "serie",
        "created_at",
    )
    list_filter = ("tipo", "status", "ambiente", "canal")
    search_fields = ("referencia", "chave_acesso", "numero", "venda__id_externo")
    autocomplete_fields = ("venda", "solicitada_por")
    readonly_fields = (
        "id_externo",
        "referencia",
        "acbr_id",
        "status",
        "ambiente",
        "chave_acesso",
        "numero",
        "serie",
        "protocolo",
        "codigo_status",
        "mensagem_sefaz",
        "valor_total",
        "autorizada_em",
        "cancelada_em",
        "ultima_sincronizacao_em",
        "created_at",
        "updated_at",
    )
    inlines = (TentativaFiscalInline, EventoFiscalInline)


@admin.register(TentativaFiscal)
class TentativaFiscalAdmin(admin.ModelAdmin):
    list_display = ("documento", "operacao", "resultado", "http_status", "iniciada_em")
    list_filter = ("operacao", "resultado")
    readonly_fields = [field.name for field in TentativaFiscal._meta.fields]


@admin.register(EventoFiscal)
class EventoFiscalAdmin(admin.ModelAdmin):
    list_display = ("documento", "tipo", "status_anterior", "status_novo", "criado_em")
    list_filter = ("tipo", "status_novo")
    readonly_fields = [field.name for field in EventoFiscal._meta.fields]

