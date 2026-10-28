from rest_framework import serializers
from decimal import Decimal
from .models import SessaoCaixa, Venda, VendaItem, VendaPagamento, OperacaoCaixa
from apps.produtos.serializers import ProdutoSimplificadoSerializer
from apps.clientes.models import Cliente

class OperacaoCaixaSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperacaoCaixa
        fields = ['id', 'tipo', 'valor', 'motivo', 'created_at']
        read_only_fields = ['id', 'created_at']


class VendaPagamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendaPagamento
        fields = ['id', 'forma', 'valor', 'created_at']
        read_only_fields = fields


class VendaItemSerializer(serializers.ModelSerializer):
    """Serializer para escrita de itens"""
    class Meta:
        model = VendaItem
        fields = ['id', 'venda', 'produto', 'quantidade', 'preco_unitario', 'subtotal']
        read_only_fields = ['id', 'preco_unitario', 'subtotal']

    def validate_quantidade(self, value):
        if value <= 0:
            raise serializers.ValidationError('A quantidade deve ser maior que zero.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        venda = self.instance.venda if self.instance else attrs.get('venda')

        if not venda:
            raise serializers.ValidationError({'venda': 'Informe a venda.'})
        if request and venda.sessao.operador_id != request.user.id:
            raise serializers.ValidationError({'venda': 'A venda pertence a outro operador.'})
        if venda.status != 'EM_ABERTO' or venda.sessao.status != 'ABERTA':
            raise serializers.ValidationError({'venda': 'A venda e o caixa devem estar abertos.'})

        if self.instance:
            if attrs.get('venda', venda).pk != self.instance.venda_id:
                raise serializers.ValidationError({'venda': 'Não é possível mover um item para outra venda.'})
            produto = attrs.get('produto', self.instance.produto)
            if produto.pk != self.instance.produto_id:
                raise serializers.ValidationError({'produto': 'Não é possível trocar o produto de um item existente.'})
        return attrs

    def create(self, validated_data):
        validated_data['preco_unitario'] = validated_data['produto'].preco_venda
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['preco_unitario'] = instance.produto.preco_venda
        return super().update(instance, validated_data)



class VendaItemReadSerializer(VendaItemSerializer):
    """Serializer para leitura de itens com detalhes do produto"""
    produto = ProdutoSimplificadoSerializer(read_only=True)

    class Meta(VendaItemSerializer.Meta):
        fields = VendaItemSerializer.Meta.fields + ['created_at']


class VendaSerializer(serializers.ModelSerializer):
    """Serializer para escrita de Venda"""
    class Meta:
        model = Venda
        fields = [
            'id', 'sessao', 'cliente', 'data',
            'total', 'desconto', 'taxa_entrega', 'canal', 'status',
            'observacoes', 'motivo_cancelamento', 'cancelada_em', 'id_externo'
        ]
        read_only_fields = [
            'id', 'data', 'total', 'desconto', 'status',
            'motivo_cancelamento', 'cancelada_em', 'id_externo',
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        sessao = self.instance.sessao if self.instance else attrs.get('sessao')

        if not sessao:
            raise serializers.ValidationError({'sessao': 'Informe a sessão de caixa.'})
        if request and sessao.operador_id != request.user.id:
            raise serializers.ValidationError({'sessao': 'A sessão pertence a outro operador.'})
        if sessao.status != 'ABERTA':
            raise serializers.ValidationError({'sessao': 'A sessão de caixa está fechada.'})
        if self.instance and attrs.get('sessao', sessao).pk != self.instance.sessao_id:
            raise serializers.ValidationError({'sessao': 'Não é possível mover uma venda para outra sessão.'})
        return attrs


class VendaReadSerializer(VendaSerializer):
    """Serializer detalhado para leitura de Venda"""
    itens = VendaItemReadSerializer(many=True, read_only=True)
    pagamentos = VendaPagamentoSerializer(many=True, read_only=True)
    cliente_nome = serializers.ReadOnlyField(source='cliente.nome')
    operador_nome = serializers.ReadOnlyField(source='sessao.operador.username')

    id_externo = serializers.ReadOnlyField()

    class Meta(VendaSerializer.Meta):
        fields = VendaSerializer.Meta.fields + ['itens', 'pagamentos', 'cliente_nome', 'operador_nome', 'created_at', 'updated_at']


class SessaoCaixaSerializer(serializers.ModelSerializer):
    operador_nome = serializers.ReadOnlyField(source='operador.username')
    operador = serializers.PrimaryKeyRelatedField(read_only=True)

    # Aliases para compatibilidade com o frontend
    aberta_em = serializers.DateTimeField(source='data_abertura', read_only=True)
    fechada_em = serializers.DateTimeField(source='data_fechamento', read_only=True, allow_null=True)

    # Campos calculados
    total_vendas = serializers.SerializerMethodField()
    total_sangrias = serializers.SerializerMethodField()
    total_suprimentos = serializers.SerializerMethodField()
    saldo_final_calculado = serializers.SerializerMethodField()

    class Meta:
        model = SessaoCaixa
        fields = [
            'id', 'operador', 'operador_nome', 'fundo_inicial',
            'data_abertura', 'data_fechamento', 'status', 'valor_contado',
            'diferenca_caixa', 'created_at',
            # campos calculados / aliases:
            'aberta_em', 'fechada_em',
            'total_vendas', 'total_sangrias', 'total_suprimentos', 'saldo_final_calculado',
        ]
        read_only_fields = [
            'id', 'operador', 'data_abertura', 'data_fechamento', 'status',
            'valor_contado', 'diferenca_caixa', 'created_at', 'aberta_em',
            'fechada_em', 'total_vendas', 'total_sangrias', 'total_suprimentos',
            'saldo_final_calculado',
        ]

    def validate_fundo_inicial(self, value):
        if value < 0:
            raise serializers.ValidationError('O fundo inicial não pode ser negativo.')
        if self.instance and value != self.instance.fundo_inicial:
            raise serializers.ValidationError('O fundo inicial não pode ser alterado após a abertura.')
        return value

    def get_total_vendas(self, obj):
        from django.db.models import Sum
        from .models import Venda
        total = Venda.objects.filter(sessao=obj, status='FINALIZADA').aggregate(t=Sum('total'))['t'] or 0
        return str(total)

    def get_total_sangrias(self, obj):
        from django.db.models import Sum
        from .models import OperacaoCaixa
        total = OperacaoCaixa.objects.filter(sessao=obj, tipo='SANGRIA').aggregate(t=Sum('valor'))['t'] or 0
        return str(total)

    def get_total_suprimentos(self, obj):
        from django.db.models import Sum
        from .models import OperacaoCaixa
        total = OperacaoCaixa.objects.filter(sessao=obj, tipo='SUPRIMENTO').aggregate(t=Sum('valor'))['t'] or 0
        return str(total)

    def get_saldo_final_calculado(self, obj):
        from django.db.models import Sum
        from .models import Venda, OperacaoCaixa
        total_dinheiro = VendaPagamento.objects.filter(
            venda__sessao=obj, venda__status='FINALIZADA', forma='DINHEIRO'
        ).aggregate(t=Sum('valor'))['t'] or 0
        total_sangrias = OperacaoCaixa.objects.filter(sessao=obj, tipo='SANGRIA').aggregate(t=Sum('valor'))['t'] or 0
        total_suprimentos = OperacaoCaixa.objects.filter(sessao=obj, tipo='SUPRIMENTO').aggregate(t=Sum('valor'))['t'] or 0
        fundo = obj.fundo_inicial or 0
        saldo = fundo + total_dinheiro + total_suprimentos - total_sangrias
        return str(saldo)


# Serializers apenas para documentação OpenAPI (Inputs de Actions)
class PagamentoInputSerializer(serializers.Serializer):
    forma = serializers.ChoiceField(choices=VendaPagamento.FORMA_CHOICES)
    valor = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))

class VendaFinalizarSerializer(serializers.Serializer):
    pagamentos = PagamentoInputSerializer(many=True, allow_empty=False)
    desconto = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=Decimal('0.00'),
        min_value=Decimal('0.00'),
    )
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(), required=False, allow_null=True
    )
