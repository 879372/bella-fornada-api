import pytest
from django.contrib.auth.models import User

from .factories import ProdutoFactory


@pytest.mark.django_db
def test_operador_pode_consultar_mas_nao_alterar_produto(api_client):
    user = User.objects.create_user(username='caixa_produto', password='senha-forte')
    product = ProdutoFactory(nome='Produto protegido')
    api_client.force_authenticate(user=user)

    read_response = api_client.get(f'/api/produtos/{product.pk}/')
    update_response = api_client.patch(
        f'/api/produtos/{product.pk}/',
        {'nome': 'Alteração indevida', 'ncm': '19059090'},
        format='json',
    )

    product.refresh_from_db()
    assert read_response.status_code == 200
    assert update_response.status_code == 403
    assert product.nome == 'Produto protegido'

