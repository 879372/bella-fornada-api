from rest_framework import serializers
from .models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
    """Serializer para escrita (POST/PUT)"""
    class Meta:
        model = Cliente
        fields = [
            'id', 'codigo_legado', 'razao_social', 'nome',
            'endereco', 'bairro', 'cidade', 'uf', 'cep',
            'telefone', 'email', 'cpf_cnpj', 'inscricao_estadual',
            'pessoa', 'regime_tributario', 'tipo_cliente',
            'data_cadastro', 'data_nascimento',
            'limite_credito', 'valor_aberto', 'observacoes', 'ativo', 'loja',
        ]


class ClienteReadSerializer(ClienteSerializer):
    """Serializer para leitura (GET)"""
    class Meta(ClienteSerializer.Meta):
        fields = ClienteSerializer.Meta.fields + ['created_at', 'updated_at']


class ClienteSimplificadoSerializer(serializers.ModelSerializer):
    """Versão leve para listagens rápidas"""
    class Meta:
        model = Cliente
        fields = ['id', 'codigo_legado', 'nome', 'cpf_cnpj']
