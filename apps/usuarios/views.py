from django.contrib.auth.models import User
from rest_framework import filters, generics, permissions, viewsets
from rest_framework.exceptions import ValidationError

from .permissions import IsAdminOrManager
from .serializers import MeuPerfilSerializer, UsuarioSerializer


class MeuPerfilView(generics.RetrieveAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = MeuPerfilSerializer

    def get_object(self):
        return self.request.user


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('perfil_bella_fornada').order_by('username')
    serializer_class = UsuarioSerializer
    permission_classes = (permissions.IsAuthenticated, IsAdminOrManager)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering_fields = ('username', 'first_name', 'last_login', 'is_active')
    http_method_names = ('get', 'post', 'patch', 'head', 'options')

    def perform_update(self, serializer):
        target = serializer.instance
        if target == self.request.user and serializer.validated_data.get('is_active') is False:
            raise ValidationError({'ativo': 'Você não pode desativar o próprio acesso.'})
        serializer.save()

