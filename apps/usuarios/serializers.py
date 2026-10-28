from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from .models import PerfilUsuario


class UsuarioSerializer(serializers.ModelSerializer):
    papel = serializers.ChoiceField(choices=PerfilUsuario.Papel.choices)
    telefone = serializers.CharField(required=False, allow_blank=True)
    ativo = serializers.BooleanField(source='is_active', required=False)
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    papel_label = serializers.CharField(
        source='perfil_bella_fornada.get_papel_display', read_only=True
    )

    class Meta:
        model = User
        fields = (
            'id', 'username', 'first_name', 'last_name', 'email', 'papel',
            'papel_label', 'telefone', 'ativo', 'password', 'last_login',
        )
        read_only_fields = ('id', 'papel_label', 'last_login')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        perfil = getattr(instance, 'perfil_bella_fornada', None)
        data['papel'] = perfil.papel if perfil else PerfilUsuario.Papel.CAIXA
        data['telefone'] = perfil.telefone if perfil else ''
        return data

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'Informe uma senha inicial.'})
        request = self.context.get('request')
        requested_role = attrs.get('papel')
        if (
            requested_role == PerfilUsuario.Papel.ADMIN
            and request
            and not request.user.is_superuser
        ):
            raise serializers.ValidationError(
                {'papel': 'Somente um administrador principal pode criar outro administrador.'}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        papel = validated_data.pop('papel')
        telefone = validated_data.pop('telefone', '')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        perfil = user.perfil_bella_fornada
        perfil.papel = papel
        perfil.telefone = telefone
        perfil.save(update_fields=('papel', 'telefone', 'updated_at'))
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        papel = validated_data.pop('papel', None)
        telefone = validated_data.pop('telefone', None)
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=('password',))
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=instance)
        changed = []
        if papel is not None:
            perfil.papel = papel
            changed.append('papel')
        if telefone is not None:
            perfil.telefone = telefone
            changed.append('telefone')
        if changed:
            perfil.save(update_fields=(*changed, 'updated_at'))
        return instance


class MeuPerfilSerializer(UsuarioSerializer):
    class Meta(UsuarioSerializer.Meta):
        fields = tuple(field for field in UsuarioSerializer.Meta.fields if field != 'password')

