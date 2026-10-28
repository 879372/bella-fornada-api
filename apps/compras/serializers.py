from rest_framework import serializers
from django.db import transaction
from .models import NotaCompra, ItemNotaCompra
from apps.produtos.serializers import ProdutoSimplificadoSerializer

class ItemNotaCompraSerializer(serializers.ModelSerializer):
    """Serializer para escrita de itens da compra."""
    class Meta:
        model = ItemNotaCompra
        fields = ['id', 'produto', 'descricao', 'quantidade', 'valor_unitario', 'subtotal']
        read_only_fields = ['id']


class ItemNotaCompraReadSerializer(ItemNotaCompraSerializer):
    """Serializer para leitura de itens com detalhes do produto"""
    produto = ProdutoSimplificadoSerializer(read_only=True)

    class Meta(ItemNotaCompraSerializer.Meta):
        fields = ItemNotaCompraSerializer.Meta.fields + ['created_at']


class NotaCompraSerializer(serializers.ModelSerializer):
    """Serializer para escrita de compra, suportando itens aninhados."""
    itens = ItemNotaCompraSerializer(many=True, required=False)

    class Meta:
        model = NotaCompra
        fields = [
            'id', 'numero_documento', 'fornecedor', 'cnpj_fornecedor',
            'data_emissao', 'data_entrada', 'valor_total',
            'status', 'observacoes', 'itens'
        ]
        read_only_fields = ['id', 'data_entrada', 'status']

    def create(self, validated_data):
        itens_data = validated_data.pop('itens', [])
        # Compras são apenas registros de entrada, sem fluxo de pendência.
        validated_data['status'] = 'RECEBIDA'

        with transaction.atomic():
            nota = NotaCompra.objects.create(**validated_data)
            for item_data in itens_data:
                item = ItemNotaCompra.objects.create(nota=nota, **item_data)
                if item.produto:
                    from apps.produtos.services import registrar_movimentacao
                    registrar_movimentacao(
                        produto_id=item.produto_id,
                        tipo='ENTRADA',
                        quantidade=item.quantidade,
                        motivo='COMPRA',
                        loja='Loja Principal',
                        observacoes=f"Entrada da compra {nota.numero_documento or nota.id}",
                    )
            return nota


class NotaCompraReadSerializer(NotaCompraSerializer):
    """Serializer detalhado para leitura da compra."""
    itens = ItemNotaCompraReadSerializer(many=True, read_only=True)

    class Meta(NotaCompraSerializer.Meta):
        fields = NotaCompraSerializer.Meta.fields + ['itens', 'created_at', 'updated_at']
