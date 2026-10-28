from rest_framework import serializers
from .models import Produto, EstoqueLoja, MovimentacaoEstoque, Grupo


class GrupoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grupo
        fields = ['id', 'nome', 'descricao', 'ativo']
        read_only_fields = ['id']


class MovimentacaoEstoqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimentacaoEstoque
        fields = ['id', 'tipo', 'motivo', 'quantidade', 'saldo_anterior', 'saldo_atual', 'observacoes', 'created_at']
        read_only_fields = ['id', 'created_at']


class EstoqueLojaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstoqueLoja
        fields = ['id', 'loja', 'quantidade', 'updated_at']


class ProdutoSerializer(serializers.ModelSerializer):
    """Serializer base para escrita (POST/PUT)"""
    estoque_inicial = serializers.DecimalField(max_digits=15, decimal_places=3, required=False, write_only=True, default=0)

    class Meta:
        model = Produto
        fields = [
            'id', 'codigo_legado', 'nome', 'codigo_barras',
            'preco_compra', 'preco_venda', 'unidade_medida',
            'grupo', 'subgrupo', 'ativo',
            'descricao_delivery', 'disponivel_delivery', 'imagem_url',
            'tempo_preparo_minutos',
            'ncm', 'cest', 'cfop', 'cst_icms', 'origem_mercadoria',
            'aliquota_icms', 'aliquota_pis', 'aliquota_cofins',
            'estoque_inicial'
        ]

    def create(self, validated_data):
        estoque_ini = validated_data.pop('estoque_inicial', 0)
        produto = super().create(validated_data)
        # Cria registro inicial de estoque
        if estoque_ini is not None:
            EstoqueLoja.objects.create(produto=produto, loja='Loja Principal', quantidade=estoque_ini)
            # Registra movimentação de ajuste inicial
            MovimentacaoEstoque.objects.create(
                produto=produto,
                tipo='ENTRADA',
                motivo='AJUSTE',
                quantidade=estoque_ini,
                saldo_anterior=0,
                saldo_atual=estoque_ini,
                observacoes='Ajuste de estoque inicial no cadastro do produto.'
            )
        return produto

    def update(self, instance, validated_data):
        novo_estoque = validated_data.pop('estoque_inicial', None)
        produto = super().update(instance, validated_data)

        if novo_estoque is not None:
            estoque_obj, created = EstoqueLoja.objects.get_or_create(produto=produto, loja='Loja Principal')
            estoque_atual = estoque_obj.quantidade
            diferenca = novo_estoque - estoque_atual

            if diferenca != 0:
                estoque_obj.quantidade = novo_estoque
                estoque_obj.save()

                MovimentacaoEstoque.objects.create(
                    produto=produto,
                    tipo='ENTRADA' if diferenca > 0 else 'SAIDA',
                    motivo='AJUSTE',
                    quantidade=abs(diferenca),
                    saldo_anterior=estoque_atual,
                    saldo_atual=novo_estoque,
                    observacoes='Ajuste manual via cadastro de produto.'
                )
        return produto


class ProdutoReadSerializer(ProdutoSerializer):
    """Serializer detalhado para leitura (GET) com estoques aninhados"""
    estoques = EstoqueLojaSerializer(many=True, read_only=True)
    estoque_atual = serializers.SerializerMethodField()

    class Meta(ProdutoSerializer.Meta):
        fields = ProdutoSerializer.Meta.fields + ['estoques', 'estoque_atual', 'created_at', 'updated_at']

    def get_estoque_atual(self, obj):
        return sum(e.quantidade for e in obj.estoques.all())


class ProdutoSimplificadoSerializer(serializers.ModelSerializer):
    """Versão leve para uso no PDV (busca rápida)"""
    class Meta:
        model = Produto
        fields = [
            'id', 'codigo_legado', 'nome', 'codigo_barras', 'preco_venda',
            'unidade_medida', 'grupo', 'disponivel_delivery',
        ]
