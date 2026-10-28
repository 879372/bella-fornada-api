from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import OrdemProducao, PerdaProducao, Receita, ReceitaIngrediente


class ReceitaIngredienteSerializer(serializers.ModelSerializer):
    ingrediente_nome = serializers.CharField(source='ingrediente.nome', read_only=True)
    unidade = serializers.CharField(source='ingrediente.unidade_medida', read_only=True)

    class Meta:
        model = ReceitaIngrediente
        fields = (
            'id', 'ingrediente', 'ingrediente_nome', 'unidade',
            'quantidade', 'percentual_perda',
        )
        read_only_fields = ('id', 'ingrediente_nome', 'unidade')


class ReceitaSerializer(serializers.ModelSerializer):
    ingredientes = ReceitaIngredienteSerializer(many=True)
    produto_nome = serializers.CharField(source='produto.nome', read_only=True)

    class Meta:
        model = Receita
        fields = (
            'id', 'produto', 'produto_nome', 'nome', 'rendimento',
            'unidade_rendimento', 'tempo_preparo_minutos', 'instrucoes',
            'ativa', 'ingredientes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'produto_nome', 'created_at', 'updated_at')

    def validate_ingredientes(self, value):
        ids = [item['ingrediente'].id for item in value]
        if not ids:
            raise serializers.ValidationError('Informe ao menos um ingrediente.')
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('Um ingrediente foi informado mais de uma vez.')
        return value

    def validate(self, attrs):
        produto = attrs.get('produto', getattr(self.instance, 'produto', None))
        ingredientes = attrs.get('ingredientes', [])
        if produto and any(item['ingrediente'].id == produto.id for item in ingredientes):
            raise serializers.ValidationError(
                {'ingredientes': 'O produto final não pode ser ingrediente dele mesmo.'}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        ingredientes = validated_data.pop('ingredientes')
        receita = Receita.objects.create(**validated_data)
        ReceitaIngrediente.objects.bulk_create(
            ReceitaIngrediente(receita=receita, **item) for item in ingredientes
        )
        return receita

    @transaction.atomic
    def update(self, instance, validated_data):
        ingredientes = validated_data.pop('ingredientes', None)
        instance = super().update(instance, validated_data)
        if ingredientes is not None:
            instance.ingredientes.all().delete()
            ReceitaIngrediente.objects.bulk_create(
                ReceitaIngrediente(receita=instance, **item) for item in ingredientes
            )
        return instance


class OrdemProducaoSerializer(serializers.ModelSerializer):
    receita_nome = serializers.CharField(source='receita.nome', read_only=True)
    produto_nome = serializers.CharField(source='receita.produto.nome', read_only=True)
    quantidade_prevista = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    criada_por_nome = serializers.CharField(source='criada_por.username', read_only=True)

    class Meta:
        model = OrdemProducao
        fields = (
            'id', 'receita', 'receita_nome', 'produto_nome', 'quantidade_lotes',
            'quantidade_prevista', 'quantidade_produzida', 'status',
            'data_planejada', 'iniciada_em', 'concluida_em', 'criada_por_nome',
            'codigo_lote', 'data_validade', 'observacoes', 'created_at',
        )
        read_only_fields = (
            'id', 'status', 'quantidade_prevista', 'quantidade_produzida',
            'iniciada_em', 'concluida_em', 'criada_por_nome', 'created_at',
        )


class ConcluirOrdemSerializer(serializers.Serializer):
    quantidade_produzida = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        required=False,
    )


class PerdaProducaoSerializer(serializers.ModelSerializer):
    produto_nome = serializers.CharField(source='produto.nome', read_only=True)
    registrada_por_nome = serializers.CharField(
        source='registrada_por.username', read_only=True
    )

    class Meta:
        model = PerdaProducao
        fields = (
            'id', 'produto', 'produto_nome', 'quantidade', 'motivo',
            'observacoes', 'registrada_por_nome', 'created_at',
        )
        read_only_fields = (
            'id', 'produto_nome', 'registrada_por_nome', 'created_at',
        )

