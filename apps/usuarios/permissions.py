from rest_framework.permissions import BasePermission

from .models import PerfilUsuario


def papel_usuario(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return PerfilUsuario.Papel.ADMIN
    perfil = getattr(user, 'perfil_bella_fornada', None)
    return perfil.papel if perfil else None


class IsAdminOrManager(BasePermission):
    message = 'Apenas administradores e gerentes podem realizar esta operação.'

    def has_permission(self, request, view):
        return papel_usuario(request.user) in {
            PerfilUsuario.Papel.ADMIN,
            PerfilUsuario.Papel.GERENTE,
        }


class HasOperationalRole(BasePermission):
    allowed_roles = set()

    def has_permission(self, request, view):
        role = papel_usuario(request.user)
        return role == PerfilUsuario.Papel.ADMIN or role in self.allowed_roles

