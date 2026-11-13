import base64

from rest_framework import serializers

from apps.vendas.models import Venda

from .crypto import encrypt_secret
from .models import (
    ConfiguracaoFiscal,
    DocumentoFiscal,
    EventoFiscal,
    InutilizacaoNumeracao,
    TentativaFiscal,
)
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


class ConfiguracaoFiscalSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    certificado = serializers.FileField(write_only=True, required=False)
    certificado_senha = serializers.CharField(write_only=True, required=False, allow_blank=True)
    csc = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_key_configurada = serializers.SerializerMethodField()
    certificado_configurado = serializers.SerializerMethodField()
    certificado_senha_configurada = serializers.SerializerMethodField()
    csc_configurado = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracaoFiscal
        fields = [
            "ambiente", "api_url", "api_key", "api_key_configurada", "certificado",
            "certificado_nome", "certificado_configurado", "certificado_senha",
            "certificado_senha_configurada", "cnpj", "inscricao_estadual",
            "razao_social", "nome_fantasia", "telefone", "email", "logradouro",
            "numero", "complemento", "bairro", "municipio", "codigo_municipio",
            "uf", "cep", "codigo_regime_tributario", "tipo_atividade", "serie_nfce",
            "proximo_numero_nfce", "serie_nfe", "proximo_numero_nfe", "csc",
            "csc_id", "csc_configurado", "updated_at",
        ]
        read_only_fields = ["certificado_nome", "updated_at"]

    def get_api_key_configurada(self, obj): return bool(obj.api_key_encrypted)
    def get_certificado_configurado(self, obj): return bool(obj.certificado_encrypted)
    def get_certificado_senha_configurada(self, obj): return bool(obj.certificado_senha_encrypted)
    def get_csc_configurado(self, obj): return bool(obj.csc_encrypted)

    def to_internal_value(self, data):
        data = data.copy()
        # Máscaras do formulário não devem estourar o max_length do model antes
        # que a validação consiga normalizar os documentos.
        for field in ("cnpj", "codigo_municipio", "cep"):
            if field in data and data[field] is not None:
                data[field] = "".join(c for c in str(data[field]) if c.isdigit())
        return super().to_internal_value(data)

    def validate_certificado(self, value):
        if not value.name.lower().endswith((".pfx", ".p12")):
            raise serializers.ValidationError("Envie um certificado A1 .pfx ou .p12.")
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("O certificado deve ter no máximo 2 MB.")
        return value

    def validate(self, attrs):
        for field, length, label in (("cnpj", 14, "CNPJ"), ("codigo_municipio", 7, "código IBGE"), ("cep", 8, "CEP")):
            if field in attrs:
                digits = "".join(c for c in str(attrs[field]) if c.isdigit())
                if digits and len(digits) != length:
                    raise serializers.ValidationError({field: f"{label} deve ter {length} dígitos."})
                attrs[field] = digits
        if "uf" in attrs:
            attrs["uf"] = attrs["uf"].strip().upper()
            if attrs["uf"] and len(attrs["uf"]) != 2:
                raise serializers.ValidationError({"uf": "Informe uma UF com 2 letras."})
        return attrs

    def update(self, instance, validated_data):
        api_key = validated_data.pop("api_key", None)
        certificado = validated_data.pop("certificado", None)
        senha = validated_data.pop("certificado_senha", None)
        csc = validated_data.pop("csc", None)
        if api_key:
            instance.api_key_encrypted = encrypt_secret(api_key)
        if certificado:
            instance.certificado_encrypted = encrypt_secret(base64.b64encode(certificado.read()).decode("ascii"))
            instance.certificado_nome = certificado.name[:255]
        if senha:
            instance.certificado_senha_encrypted = encrypt_secret(senha)
        if csc:
            instance.csc_encrypted = encrypt_secret(csc)
        return super().update(instance, validated_data)


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
        return bool(obj.xml_conteudo)

    def get_pode_baixar_pdf(self, obj):
        return bool(obj.pdf_conteudo)


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


class InutilizacaoNumeracaoSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    pode_baixar_xml = serializers.SerializerMethodField()

    class Meta:
        model = InutilizacaoNumeracao
        fields = [
            "id_externo",
            "tipo",
            "tipo_display",
            "ambiente",
            "status",
            "status_display",
            "serie",
            "ano",
            "numero_inicial",
            "numero_final",
            "justificativa",
            "codigo_status",
            "mensagem_sefaz",
            "protocolo",
            "pode_baixar_xml",
            "created_at",
        ]
        read_only_fields = fields

    def get_pode_baixar_xml(self, obj):
        return bool(obj.xml_conteudo)


class SolicitarInutilizacaoNumeracaoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=DocumentoFiscal.Tipo.choices)
    serie = serializers.RegexField(r"^[0-9]{1,3}$")
    ano = serializers.IntegerField(min_value=2000, max_value=2099)
    numero_inicial = serializers.IntegerField(min_value=1)
    numero_final = serializers.IntegerField(min_value=1)
    justificativa = serializers.CharField(min_length=15, max_length=255, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["numero_final"] < attrs["numero_inicial"]:
            raise serializers.ValidationError(
                {"numero_final": "O número final não pode ser menor que o inicial."}
            )
        return attrs


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

