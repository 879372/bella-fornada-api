import re

from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import PerfilUsuario
from .permissions import papel_usuario

LEITURA = frozenset({'GET', 'HEAD', 'OPTIONS'})
TODOS = None

# Rotas que o PDV usa. Qualquer outra rota da API é do painel administrativo.
ROTAS_PDV = (
    (re.compile(r'^/api/auth/'), TODOS),
    (re.compile(r'^/api/sessoes-caixa/gestao/'), frozenset()),
    (re.compile(r'^/api/sessoes-caixa/'), TODOS),
    (re.compile(r'^/api/vendas/'), TODOS),
    (re.compile(r'^/api/venda-itens/'), TODOS),
    (re.compile(r'^/api/produtos/(\d+/)?preco-pdv/'), TODOS),
    (re.compile(r'^/api/produtos/'), LEITURA),
    (re.compile(r'^/api/clientes/'), LEITURA),
    (re.compile(r'^/api/fiscal/documentos/emitir/'), TODOS),
    (re.compile(r'^/api/fiscal/documentos/'), LEITURA),
)


def rota_liberada_para_caixa(path, method):
    for padrao, metodos in ROTAS_PDV:
        if padrao.match(path):
            return metodos is TODOS or method in metodos
    return False


def eh_somente_pdv(user):
    return papel_usuario(user) == PerfilUsuario.Papel.CAIXA and not user.is_staff


class PerfilJWTAuthentication(JWTAuthentication):
    """JWT que restringe o papel Caixa às rotas do PDV.

    Fica na autenticação, e não numa permissão, para valer também nas views
    que definem `permission_classes` próprias.
    """

    def authenticate(self, request):
        resultado = super().authenticate(request)
        if resultado is None:
            return None
        user, _token = resultado
        if (eh_somente_pdv(user)
                and not rota_liberada_para_caixa(request.path, request.method)):
            raise PermissionDenied('O usuário caixa tem acesso apenas ao PDV.')
        return resultado
