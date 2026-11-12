from decimal import Decimal

from django.utils import timezone

from rest_framework import serializers

from .barcodes import gtin_valido
from .fiscal_codes import NORMAL_ICMS_CST, PIS_COFINS_CST, SIMPLES_CSOSN
from .models import ConfiguracaoBalanca, EstoqueLoja, Grupo, MovimentacaoEstoque, Produto


class GrupoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grupo
        fields = ['id', 'nome', 'descricao', 'ativo']
        read_only_fields = ['id']


class ConfiguracaoBalancaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracaoBalanca
        fields = [
            'id', 'nome', 'fabricante', 'modelo', 'versao_mgv', 'ip', 'porta',
            'departamento', 'validade_padrao_dias', 'prefixo_ean', 'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']

    def validate_prefixo_ean(self, value):
        if len(value) != 1 or not value.isdigit():
            raise serializers.ValidationError('Informe um prefixo numérico de um dígito.')
        return value


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
            'grupo', 'subgrupo', 'marca', 'ativo',
            'descricao_delivery', 'disponivel_delivery', 'imagem_url',
            'tempo_preparo_minutos',
            'ncm', 'cest', 'cfop', 'cst_icms', 'cst_pis', 'cst_cofins',
            'origem_mercadoria', 'codigo_beneficio_fiscal',
            'unidade_tributavel', 'gtin_tributavel',
            'fator_conversao_tributavel',
            'aliquota_icms', 'aliquota_pis', 'aliquota_cofins',
            'tipo_origem_comercial', 'fiscal_confianca',
            'fiscal_fonte', 'fiscal_observacao', 'fiscal_revisado_em',
            'estoque_inicial'
        ]
        read_only_fields = ['fiscal_revisado_em']

    def validate_ncm(self, value):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if not digits:
            return ''
        if len(digits) != 8 or digits == '00000000':
            raise serializers.ValidationError('Informe um NCM válido com 8 dígitos.')
        return digits

    def validate_cfop(self, value):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if len(digits) != 4 or digits[0] not in set('123567'):
            raise serializers.ValidationError('Informe um CFOP válido com 4 dígitos.')
        return digits

    def validate_cest(self, value):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if digits and len(digits) != 7:
            raise serializers.ValidationError('Informe um CEST válido com 7 dígitos.')
        return digits

    def validate_cst_icms(self, value):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if digits not in SIMPLES_CSOSN | NORMAL_ICMS_CST:
            raise serializers.ValidationError('Informe um CST/CSOSN válido.')
        return digits

    def _validate_cst_contribuicao(self, value, label):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if digits and digits not in PIS_COFINS_CST:
            raise serializers.ValidationError(f'Informe um CST {label} válido.')
        return digits

    def validate_cst_pis(self, value):
        return self._validate_cst_contribuicao(value, 'PIS')

    def validate_cst_cofins(self, value):
        return self._validate_cst_contribuicao(value, 'COFINS')

    def validate_gtin_tributavel(self, value):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if digits and not gtin_valido(digits):
            raise serializers.ValidationError(
                'Informe um GTIN comercial válido; etiquetas de balança e códigos internos não são GTIN.'
            )
        return digits

    def validate_unidade_tributavel(self, value):
        return str(value or '').strip().upper()[:6]

    def validate_origem_mercadoria(self, value):
        digits = ''.join(character for character in str(value or '') if character.isdigit())
        if digits not in set('012345678'):
            raise serializers.ValidationError('A origem da mercadoria deve estar entre 0 e 8.')
        return digits

    def validate(self, attrs):
        attrs = super().validate(attrs)
        fator = attrs.get(
            'fator_conversao_tributavel',
            getattr(self.instance, 'fator_conversao_tributavel', 1),
        )
        if fator is not None and (
            not fator.is_finite()
            or fator <= 0
            or fator > Decimal('999999999.999999')
        ):
            raise serializers.ValidationError({
                'fator_conversao_tributavel': 'O fator de conversão deve ser maior que zero.'
            })

        rate_errors = {}
        for field in ('aliquota_icms', 'aliquota_pis', 'aliquota_cofins'):
            rate = attrs.get(field, getattr(self.instance, field, Decimal('0')))
            if not rate.is_finite() or not Decimal('0') <= rate <= Decimal('100'):
                rate_errors[field] = 'A alíquota deve estar entre 0 e 100.'
        if rate_errors:
            raise serializers.ValidationError(rate_errors)

        current = self.instance
        confidence = attrs.get(
            'fiscal_confianca',
            getattr(current, 'fiscal_confianca', Produto.ConfiancaFiscal.NAO_REVISADO),
        )
        source = attrs.get('fiscal_fonte', getattr(current, 'fiscal_fonte', ''))
        if confidence in {
            Produto.ConfiancaFiscal.ALTA,
            Produto.ConfiancaFiscal.MEDIA,
        } and not str(source or '').strip():
            raise serializers.ValidationError({
                'fiscal_fonte': 'Informe a fonte da revisão fiscal.'
            })
        if confidence == Produto.ConfiancaFiscal.ALTA:
            required = {
                'ncm': 'NCM',
                'cst_pis': 'CST PIS',
                'cst_cofins': 'CST COFINS',
                'unidade_tributavel': 'Unidade tributável',
            }
            errors = {
                field: f'{label} é obrigatório para confiança alta.'
                for field, label in required.items()
                if not attrs.get(field, getattr(current, field, ''))
            }
            commercial_origin = attrs.get(
                'tipo_origem_comercial',
                getattr(
                    current,
                    'tipo_origem_comercial',
                    Produto.TipoOrigemComercial.NAO_CLASSIFICADO,
                ),
            )
            if commercial_origin == Produto.TipoOrigemComercial.NAO_CLASSIFICADO:
                errors['tipo_origem_comercial'] = (
                    'Informe a origem comercial para confiança alta.'
                )
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

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
        fiscal_fields = {
            'ncm', 'cest', 'cfop', 'cst_icms', 'cst_pis', 'cst_cofins',
            'origem_mercadoria', 'codigo_beneficio_fiscal',
            'unidade_tributavel', 'gtin_tributavel',
            'fator_conversao_tributavel', 'aliquota_icms', 'aliquota_pis',
            'aliquota_cofins', 'tipo_origem_comercial', 'fiscal_confianca',
            'fiscal_fonte', 'fiscal_observacao',
        }
        if any(
            field in validated_data
            and getattr(instance, field) != validated_data[field]
            for field in fiscal_fields
        ):
            validated_data['fiscal_revisado_em'] = timezone.now()
        # O saldo é alterado exclusivamente pelo fluxo de ajuste/Kardex.
        # Isso impede que uma edição cadastral/fiscal regrave um estoque antigo.
        validated_data.pop('estoque_inicial', None)
        return super().update(instance, validated_data)


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
