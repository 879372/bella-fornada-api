import pytest

from apps.usuarios.models import PerfilUsuario


@pytest.mark.django_db
def test_superusuario_recebe_perfil_admin(admin_user):
    assert admin_user.perfil_bella_fornada.papel == PerfilUsuario.Papel.ADMIN


@pytest.mark.django_db
def test_admin_cria_usuario_com_senha_hash(auth_client):
    response = auth_client.post('/api/usuarios/', {
        'username': 'caixa1',
        'first_name': 'Caixa',
        'papel': 'CAIXA',
        'password': 'senha-segura-123',
        'ativo': True,
    }, format='json')

    assert response.status_code == 201
    from django.contrib.auth.models import User

    user = User.objects.get(username='caixa1')
    assert user.check_password('senha-segura-123')
    assert user.perfil_bella_fornada.papel == PerfilUsuario.Papel.CAIXA

