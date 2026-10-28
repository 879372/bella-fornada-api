import pytest


@pytest.mark.django_db
def test_health_check_publico(api_client):
    response = api_client.get('/api/health/')
    assert response.status_code == 200
    assert response.data['status'] == 'ok'
    assert response.data['database'] == 'connected'


@pytest.mark.django_db
def test_login_jwt(api_client, admin_user):
    response = api_client.post('/api/auth/login/', {
        'username': admin_user.username,
        'password': 'testpassword123',
    }, format='json')
    assert response.status_code == 200
    assert response.data['access']
    assert response.data['refresh']


@pytest.mark.django_db
def test_dashboard_exige_autenticacao(api_client):
    response = api_client.get('/api/dashboard-stats/')
    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_renova_sessao_com_validade_longa(api_client, admin_user):
    """Cada renovação devolve um refresh novo com ~1 ano de validade (sessão deslizante)."""
    import time
    from rest_framework_simplejwt.tokens import RefreshToken

    login = api_client.post('/api/auth/login/', {
        'username': 'admin_test', 'password': 'testpassword123',
    }, format='json')
    assert login.status_code == 200

    refresh = api_client.post('/api/auth/refresh/', {'refresh': login.data['refresh']}, format='json')
    assert refresh.status_code == 200
    assert refresh.data['access']
    assert refresh.data['refresh'] != login.data['refresh']

    dias_restantes = (RefreshToken(refresh.data['refresh'])['exp'] - time.time()) / 86400
    assert dias_restantes > 360
