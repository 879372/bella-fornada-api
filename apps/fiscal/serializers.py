from rest_framework import serializers

from apps.vendas.models import Venda

from .models import DocumentoFiscal, EventoFiscal, TentativaFiscal
from .services.fiscal import FiscalService


class TentativaFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = TentativaFiscal
        fields = [
            "id",
            "operacao",
            "resultado",
            "http_status",
            "status_remoto",
            "codigo_erro",
            "mensagem",
            "iniciada_em",
            "finalizada_em",
        ]
        read_only_fields = fields


class EventoFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoFiscal
        fields = [
            "id",
            "tipo",
            "status_anterior",
            "status_novo",
            "descricao",
            "criado_em",
        ]
        read_only_fields = fields


class DocumentoFiscalSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    venda_numero = serializers.IntegerField(source="venda_id", read_only=True)
    venda_total = serializers.DecimalField(
        source="venda.total_liquido",
        max_digits=15,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    ultima_tentativa = serializers.SerializerMethodField()
    pode_baixar_xml = serializers.SerializerMethodField()
    pode_baixar_pdf = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoFiscal
        fields = [
            "id",
            "id_externo",
            "venda",
            "venda_numero",
            "venda_total",
            "pedido_delivery_id",
            "canal",
            "tipo",
            "tipo_display",
            "status",
            "status_display",
            "ambiente",
            "referencia",
            "acbr_id",
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
            "pode_baixar_xml",
            "pode_baixar_pdf",
            "ultima_tentativa",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_ultima_tentativa(self, obj):
        attempts = list(obj.tentativas.all())
        if not attempts:
            return None
        return TentativaFiscalSerializer(attempts[0]).data

    def get_pode_baixar_xml(self, obj):
        return bool(
            obj.acbr_id
            and obj.status
            in {DocumentoFiscal.Status.AUTORIZADA, DocumentoFiscal.Status.CANCELADA}
        )

    def get_pode_baixar_pdf(self, obj):
        return bool(obj.acbr_id and obj.status == DocumentoFiscal.Status.AUTORIZADA)


class EmitirDocumentoFiscalSerializer(serializers.Serializer):
    venda = serializers.PrimaryKeyRelatedField(queryset=Venda.objects.all())
    tipo = serializers.ChoiceField(choices=DocumentoFiscal.Tipo.choices)
    canal = serializers.ChoiceField(
        choices=DocumentoFiscal.Canal.choices,
        required=False,
    )
    pedido_delivery_id = serializers.UUIDField(required=False, allow_null=True)
    referencia = serializers.CharField(max_length=100, required=False)

    def validate_referencia(self, value):
        return FiscalService.normalize_reference(value)

    def validate(self, attrs):
        venda = attrs["venda"]
        if venda.status != "FINALIZADA":
            raise serializers.ValidationError(
                {"venda": "Somente vendas finalizadas podem emitir documento fiscal."}
            )
        if not venda.itens.exists():
            raise serializers.ValidationError({"venda": "A venda não possui itens."})

        canal = attrs.get("canal")
        if not canal:
            attrs["canal"] = (
                DocumentoFiscal.Canal.DELIVERY
                if getattr(venda, "canal", "") == "DELIVERY"
                else DocumentoFiscal.Canal.PDV
            )
        if attrs["canal"] == DocumentoFiscal.Canal.DELIVERY and not attrs.get(
            "pedido_delivery_id"
        ):
            # Vendas originadas do delivery podem ainda não ter o UUID durante
            # uma importação legada; o campo continua opcional no banco.
            attrs["pedido_delivery_id"] = None
        return attrs


class CancelarDocumentoFiscalSerializer(serializers.Serializer):
    justificativa = serializers.CharField(min_length=15, max_length=255, trim_whitespace=True)


class VendaElegivelFiscalSerializer(serializers.ModelSerializer):
    id_externo = serializers.UUIDField(read_only=True)
    total_liquido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True, allow_null=True)
    operador_nome = serializers.CharField(source="sessao.operador.username", read_only=True)
    itens_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Venda
        fields = [
            "id",
            "id_externo",
            "data",
            "canal",
            "total",
            "desconto",
            "taxa_entrega",
            "total_liquido",
            "cliente_nome",
            "operador_nome",
            "itens_count",
        ]
        read_only_fields = fields

