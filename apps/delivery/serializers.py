import re
from datetime import time
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.produtos.models import Produto

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
    delivery_esta_aberto,
)


CENTAVOS = Decimal("0.01")


def moeda(valor):
    return Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def normalizar_telefone(value):
    digitos = "".join(filter(str.isdigit, value or ""))
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        digitos = digitos[2:]
    if len(digitos) not in (10, 11) or digitos.startswith("0"):
        raise serializers.ValidationError(
            "Informe um telefone com DDD. Ex.: (85) 99999-9999."
        )
    separador = 7 if len(digitos) == 11 else 6
    return f"({digitos[:2]}) {digitos[2:separador]}-{digitos[separador:]}"


class ConfiguracaoDeliverySerializer(serializers.ModelSerializer):
    esta_aberto = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracaoDelivery
        fields = (
            "id",
            "nome_loja",
            "slug",
            "whatsapp",
            "pix_chave",
            "pix_beneficiario",
            "aceita_pedidos",
            "esta_aberto",
            "horarios_funcionamento",
            "tempo_retirada_minutos",
            "tempo_entrega_minutos",
            "loja_estoque",
            "updated_at",
        )
        read_only_fields = ("id", "esta_aberto", "updated_at")

    def get_esta_aberto(self, obj):
        return delivery_esta_aberto(obj)

    def validate_whatsapp(self, value):
        digitos = re.sub(r"\D", "", value or "")
        if digitos and not 12 <= len(digitos) <= 13:
            raise serializers.ValidationError(
                "Informe o WhatsApp com DDI e DDD. Ex.: 55 85 99999-9999."
            )
        return digitos

    def validate_horarios_funcionamento(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Horários inválidos.")
        normalizado = {}
        for dia in range(7):
            faixa = value.get(str(dia)) or {
                "aberto": False,
                "inicio": "06:00",
                "fim": "20:00",
            }
            if not isinstance(faixa, dict):
                raise serializers.ValidationError("Horários inválidos.")
            try:
                inicio = time.fromisoformat(str(faixa.get("inicio", "")))
                fim = time.fromisoformat(str(faixa.get("fim", "")))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    "Use horários no formato HH:MM."
                ) from exc
            normalizado[str(dia)] = {
                "aberto": bool(faixa.get("aberto")),
                "inicio": inicio.strftime("%H:%M"),
                "fim": fim.strftime("%H:%M"),
            }
        return normalizado

    def _validar_tempo(self, value):
        if not 1 <= value <= 240:
            raise serializers.ValidationError("Informe um tempo entre 1 e 240 minutos.")
        return value

    validate_tempo_retirada_minutos = _validar_tempo
    validate_tempo_entrega_minutos = _validar_tempo


class BairroEntregaSerializer(serializers.ModelSerializer):
    class Meta:
        model = BairroEntrega
        fields = ("id", "nome", "taxa_entrega", "ativo", "ordem")

    def validate_nome(self, value):
        nome = " ".join(value.split())
        duplicados = BairroEntrega.objects.filter(nome__iexact=nome)
        if self.instance:
            duplicados = duplicados.exclude(pk=self.instance.pk)
        if duplicados.exists():
            raise serializers.ValidationError("Já existe um bairro com esse nome.")
        return nome


class GrupoComplementoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrupoComplemento
        fields = ("id", "nome", "descricao", "ativo", "ordem")

    def validate_nome(self, value):
        nome = " ".join(value.split())
        duplicados = GrupoComplemento.objects.filter(nome__iexact=nome)
        if self.instance:
            duplicados = duplicados.exclude(pk=self.instance.pk)
        if duplicados.exists():
            raise serializers.ValidationError("Já existe um grupo com esse nome.")
        return nome


class ComplementoSerializer(serializers.ModelSerializer):
    grupo_nome = serializers.CharField(source="grupo.nome", read_only=True)

    class Meta:
        model = Complemento
        fields = (
            "id",
            "grupo",
            "grupo_nome",
            "nome",
            "preco_adicional",
            "ativo",
            "ordem",
        )

    def validate(self, attrs):
        grupo = attrs.get("grupo", getattr(self.instance, "grupo", None))
        nome = " ".join(attrs.get("nome", getattr(self.instance, "nome", "")).split())
        duplicados = Complemento.objects.filter(grupo=grupo, nome__iexact=nome)
        if self.instance:
            duplicados = duplicados.exclude(pk=self.instance.pk)
        if duplicados.exists():
            raise serializers.ValidationError(
                {"nome": "Já existe um complemento com esse nome no grupo."}
            )
        attrs["nome"] = nome
        return attrs


class ProdutoGrupoComplementoSerializer(serializers.ModelSerializer):
    produto_nome = serializers.CharField(source="produto.nome", read_only=True)
    grupo_nome = serializers.CharField(source="grupo.nome", read_only=True)

    class Meta:
        model = ProdutoGrupoComplemento
        fields = (
            "id",
            "produto",
            "produto_nome",
            "grupo",
            "grupo_nome",
            "minimo_escolhas",
            "maximo_escolhas",
            "ordem",
        )

    def validate(self, attrs):
        minimo = attrs.get(
            "minimo_escolhas", getattr(self.instance, "minimo_escolhas", 0)
        )
        maximo = attrs.get(
            "maximo_escolhas", getattr(self.instance, "maximo_escolhas", 1)
        )
        if maximo < 1 or minimo > maximo:
            raise serializers.ValidationError(
                {"maximo_escolhas": "O máximo deve ser positivo e maior ou igual ao mínimo."}
            )
        return attrs


class EntregadorSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.CharField(source="usuario.username", read_only=True)

    class Meta:
        model = Entregador
        fields = ("id", "nome", "telefone", "usuario", "usuario_nome", "ativo")

    def validate_telefone(self, value):
        if not value:
            return ""
        return normalizar_telefone(value)


class PedidoItemComplementoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PedidoItemComplemento
        fields = (
            "id",
            "complemento",
            "grupo_nome",
            "complemento_nome",
            "preco_adicional",
        )


class PedidoItemSerializer(serializers.ModelSerializer):
    complementos = PedidoItemComplementoSerializer(many=True, read_only=True)

    class Meta:
        model = PedidoItem
        fields = (
            "id",
            "produto",
            "produto_nome",
            "unidade_medida",
            "preco_base_unitario",
            "preco_complementos_unitario",
            "preco_unitario",
            "quantidade",
            "subtotal",
            "observacoes",
            "complementos",
        )


class HistoricoPedidoSerializer(serializers.ModelSerializer):
    alterado_por_nome = serializers.CharField(
        source="alterado_por.username", read_only=True, default=None
    )
    tipo_label = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = HistoricoPedido
        fields = (
            "id",
            "tipo",
            "tipo_label",
            "status_anterior",
            "status_novo",
            "observacao",
            "alterado_por_nome",
            "created_at",
        )


class PedidoDeliverySerializer(serializers.ModelSerializer):
    itens = PedidoItemSerializer(many=True, read_only=True)
    historico = HistoricoPedidoSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    fulfillment_label = serializers.CharField(
        source="get_fulfillment_display", read_only=True
    )
    payment_method_label = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    bairro_exibicao = serializers.CharField(read_only=True)
    entregador_dados = EntregadorSerializer(source="entregador", read_only=True)
    tracking_url = serializers.SerializerMethodField()
    whatsapp_url = serializers.SerializerMethodField()
    pix_chave = serializers.SerializerMethodField()
    pix_beneficiario = serializers.SerializerMethodField()

    class Meta:
        model = PedidoDelivery
        fields = (
            "id",
            "rastreamento_token",
            "status",
            "status_label",
            "fulfillment",
            "fulfillment_label",
            "payment_method",
            "payment_method_label",
            "pagamento_confirmado",
            "pagamento_confirmado_em",
            "nome_cliente",
            "telefone_cliente",
            "bairro",
            "bairro_exibicao",
            "bairro_outro",
            "cep",
            "endereco",
            "numero",
            "complemento",
            "referencia",
            "cidade",
            "uf",
            "troco_para",
            "observacoes",
            "subtotal",
            "taxa_entrega",
            "total",
            "tempo_estimado_minutos",
            "entregador",
            "entregador_dados",
            "venda",
            "motivo_cancelamento",
            "concluido_em",
            "cancelado_em",
            "created_at",
            "updated_at",
            "itens",
            "historico",
            "tracking_url",
            "whatsapp_url",
            "pix_chave",
            "pix_beneficiario",
        )
        read_only_fields = fields

    def _configuracao(self):
        if not hasattr(self, "_configuracao_cache"):
            self._configuracao_cache = ConfiguracaoDelivery.atual()
        return self._configuracao_cache

    def get_tracking_url(self, obj):
        # Link da tela de acompanhamento no frontend, não do endpoint JSON.
        return f"{settings.FRONTEND_PUBLIC_URL}/acompanhar/{obj.rastreamento_token}"

    def get_pix_chave(self, obj):
        return self._configuracao().pix_chave

    def get_pix_beneficiario(self, obj):
        return self._configuracao().pix_beneficiario

    def get_whatsapp_url(self, obj):
        numero = self._configuracao().whatsapp
        if not numero:
            return ""
        linhas = [
            f"*PEDIDO #{obj.pk} - {self._configuracao().nome_loja.upper()}*",
            "",
        ]
        for item in obj.itens.all():
            linhas.append(
                f"{item.quantidade.normalize()}x {item.produto_nome} — R$ {item.subtotal:.2f}"
            )
            grupos = {}
            for adicional in item.complementos.all():
                nome = adicional.complemento_nome
                if adicional.preco_adicional:
                    nome += f" (+R$ {adicional.preco_adicional:.2f})"
                grupos.setdefault(adicional.grupo_nome, []).append(nome)
            for grupo, nomes in grupos.items():
                linhas.append(f"  • {grupo}: {', '.join(nomes)}")
            if item.observacoes:
                linhas.append(f"  Obs.: {item.observacoes}")
        linhas.extend(
            [
                "",
                f"Subtotal: R$ {obj.subtotal:.2f}",
                f"Taxa de entrega: R$ {obj.taxa_entrega:.2f}",
                f"*Total: R$ {obj.total:.2f}*",
                f"Cliente: {obj.nome_cliente}",
                f"Telefone: {obj.telefone_cliente}",
                f"Tipo: {obj.get_fulfillment_display()}",
                f"Pagamento: {obj.get_payment_method_display()}",
            ]
        )
        if obj.fulfillment == PedidoDelivery.TipoAtendimento.ENTREGA:
            linhas.extend(
                [
                    f"Endereço: {obj.endereco}, {obj.numero}",
                    f"Bairro: {obj.bairro_exibicao}",
                    f"CEP: {obj.cep} — {obj.cidade}/{obj.uf}",
                    f"Complemento: {obj.complemento or '-'}",
                    f"Referência: {obj.referencia or '-'}",
                ]
            )
        if obj.observacoes:
            linhas.extend(["", f"Observações: {obj.observacoes}"])
        return f"https://wa.me/{numero}?text={quote(chr(10).join(linhas))}"


class PedidoItemInputSerializer(serializers.Serializer):
    produto = serializers.PrimaryKeyRelatedField(
        queryset=Produto.objects.filter(ativo=True)
    )
    quantidade = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=Decimal("0.001"),
        max_value=Decimal("1000"),
    )
    complementos = serializers.PrimaryKeyRelatedField(
        queryset=Complemento.objects.filter(ativo=True, grupo__ativo=True),
        many=True,
        required=False,
    )
    observacoes = serializers.CharField(
        max_length=240, required=False, allow_blank=True
    )

    def validate(self, attrs):
        produto = attrs["produto"]
        if not getattr(produto, "disponivel_delivery", False):
            raise serializers.ValidationError(
                {"produto": "Este produto não está disponível no delivery."}
            )

        complementos = attrs.get("complementos", [])
        ids = [complemento.pk for complemento in complementos]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                {"complementos": "Um complemento foi escolhido mais de uma vez."}
            )

        vinculos = {
            vinculo.grupo_id: vinculo
            for vinculo in produto.grupos_complementos_delivery.select_related(
                "grupo"
            ).filter(grupo__ativo=True)
        }
        for complemento in complementos:
            if complemento.grupo_id not in vinculos:
                raise serializers.ValidationError(
                    {
                        "complementos": (
                            f"O complemento {complemento.nome} não pertence ao produto "
                            f"{produto.nome}."
                        )
                    }
                )
        for vinculo in vinculos.values():
            escolhidos = sum(
                1 for complemento in complementos if complemento.grupo_id == vinculo.grupo_id
            )
            if escolhidos < vinculo.minimo_escolhas:
                raise serializers.ValidationError(
                    {
                        "complementos": (
                            f"Escolha pelo menos {vinculo.minimo_escolhas} opção(ões) "
                            f"em {vinculo.grupo.nome} ({produto.nome})."
                        )
                    }
                )
            if escolhidos > vinculo.maximo_escolhas:
                raise serializers.ValidationError(
                    {
                        "complementos": (
                            f"Escolha no máximo {vinculo.maximo_escolhas} opção(ões) "
                            f"em {vinculo.grupo.nome} ({produto.nome})."
                        )
                    }
                )

        preco_base = moeda(produto.preco_venda)
        preco_complementos = moeda(
            sum((complemento.preco_adicional for complemento in complementos), Decimal("0"))
        )
        attrs["preco_base_unitario"] = preco_base
        attrs["preco_complementos_unitario"] = preco_complementos
        attrs["preco_unitario"] = moeda(preco_base + preco_complementos)
        return attrs


class CriarPedidoDeliverySerializer(serializers.ModelSerializer):
    itens = PedidoItemInputSerializer(many=True, allow_empty=False)

    class Meta:
        model = PedidoDelivery
        fields = (
            "nome_cliente",
            "telefone_cliente",
            "fulfillment",
            "payment_method",
            "bairro",
            "bairro_outro",
            "cep",
            "endereco",
            "numero",
            "complemento",
            "referencia",
            "cidade",
            "uf",
            "troco_para",
            "observacoes",
            "itens",
        )

    def validate_nome_cliente(self, value):
        return " ".join(value.split())

    def validate_telefone_cliente(self, value):
        return normalizar_telefone(value)

    def validate_cep(self, value):
        digitos = re.sub(r"\D", "", value or "")
        if digitos and len(digitos) != 8:
            raise serializers.ValidationError("Informe um CEP com 8 dígitos.")
        return f"{digitos[:5]}-{digitos[5:]}" if digitos else ""

    def validate_uf(self, value):
        return (value or "").strip().upper()

    def validate(self, attrs):
        configuracao = self.context["configuracao"]
        if not delivery_esta_aberto(configuracao):
            raise serializers.ValidationError(
                "A loja está fora do horário de atendimento do delivery."
            )

        entrega = attrs["fulfillment"] == PedidoDelivery.TipoAtendimento.ENTREGA
        bairro = attrs.get("bairro")
        bairro_outro = " ".join(attrs.get("bairro_outro", "").split())
        attrs["bairro_outro"] = bairro_outro
        if entrega:
            obrigatorios = {
                "cep": "Informe o CEP.",
                "endereco": "Informe o endereço.",
                "numero": "Informe o número.",
                "cidade": "Informe a cidade.",
                "uf": "Informe a UF.",
            }
            erros = {
                campo: mensagem
                for campo, mensagem in obrigatorios.items()
                if not attrs.get(campo)
            }
            if not bairro and not bairro_outro:
                erros["bairro"] = "Informe um bairro cadastrado ou digite o bairro."
            if bairro and not bairro.ativo:
                erros["bairro"] = "Este bairro não está disponível para entrega."
            if erros:
                raise serializers.ValidationError(erros)
            if bairro:
                attrs["bairro_outro"] = ""
        else:
            for campo in (
                "bairro_outro",
                "cep",
                "endereco",
                "numero",
                "complemento",
                "referencia",
                "cidade",
                "uf",
            ):
                attrs[campo] = ""
            attrs["bairro"] = None

        if attrs["payment_method"] != PedidoDelivery.FormaPagamento.DINHEIRO:
            attrs["troco_para"] = None
        return attrs

    def create(self, validated_data):
        itens = validated_data.pop("itens")
        configuracao = self.context["configuracao"]
        idempotency_key = self.context["idempotency_key"]
        fingerprint = self.context["request_fingerprint"]

        subtotal = moeda(
            sum(
                (item["preco_unitario"] * item["quantidade"] for item in itens),
                Decimal("0"),
            )
        )
        bairro = validated_data.get("bairro")
        taxa = moeda(bairro.taxa_entrega if bairro else 0)
        if validated_data["fulfillment"] == PedidoDelivery.TipoAtendimento.RETIRADA:
            taxa = Decimal("0.00")
        total = moeda(subtotal + taxa)
        troco_para = validated_data.get("troco_para")
        if troco_para is not None and moeda(troco_para) < total:
            raise serializers.ValidationError(
                {"troco_para": "O valor para troco deve ser igual ou maior que o total."}
            )

        inicial = (
            PedidoDelivery.Status.AGUARDANDO_PAGAMENTO
            if validated_data["payment_method"] == PedidoDelivery.FormaPagamento.PIX
            else PedidoDelivery.Status.RECEBIDO
        )
        tempo_configurado = (
            configuracao.tempo_entrega_minutos
            if validated_data["fulfillment"] == PedidoDelivery.TipoAtendimento.ENTREGA
            else configuracao.tempo_retirada_minutos
        )
        maior_preparo = max(
            (getattr(item["produto"], "tempo_preparo_minutos", 0) for item in itens),
            default=0,
        )

        with transaction.atomic():
            pedido = PedidoDelivery.objects.create(
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                status=inicial,
                bairro_nome=bairro.nome if bairro else validated_data.get("bairro_outro", ""),
                subtotal=subtotal,
                taxa_entrega=taxa,
                total=total,
                tempo_estimado_minutos=max(tempo_configurado, maior_preparo),
                **validated_data,
            )
            for dados_item in itens:
                complementos = dados_item.pop("complementos", [])
                produto = dados_item.pop("produto")
                quantidade = dados_item["quantidade"]
                item = PedidoItem.objects.create(
                    pedido=pedido,
                    produto=produto,
                    produto_nome=produto.nome,
                    unidade_medida=produto.unidade_medida,
                    subtotal=moeda(dados_item["preco_unitario"] * quantidade),
                    **dados_item,
                )
                PedidoItemComplemento.objects.bulk_create(
                    [
                        PedidoItemComplemento(
                            item=item,
                            complemento=complemento,
                            grupo_nome=complemento.grupo.nome,
                            complemento_nome=complemento.nome,
                            preco_adicional=complemento.preco_adicional,
                        )
                        for complemento in complementos
                    ]
                )
            HistoricoPedido.objects.create(
                pedido=pedido,
                tipo=HistoricoPedido.Tipo.CRIACAO,
                status_novo=inicial,
                observacao="Pedido criado pelo cardápio online.",
            )
        return pedido
