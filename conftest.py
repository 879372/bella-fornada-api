import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User

@pytest.fixture
def api_client():
    """
    Retorna uma instância do APIClient do DRF para testes de integração.
    """
    return APIClient()

@pytest.fixture
def admin_user(db):
    """
    Cria e retorna um usuário admin pré-autenticado para testes de permissão.
    """
    user = User.objects.create_superuser(
        username='admin_test',
        email='admin@test.com',
        password='testpassword123'
    )
    return user

@pytest.fixture
def auth_client(api_client, admin_user):
    """
    Retorna o APIClient já autenticado com o usuário admin.
    """
    api_client.force_authenticate(user=admin_user)
    return api_client
