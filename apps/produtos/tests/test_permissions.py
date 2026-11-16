from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from apps.usuarios.models import PerfilUsuario

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


@pytest.mark.django_db
def test_caixa_pode_alterar_somente_preco_pelo_endpoint_do_pdv(api_client):
    user = User.objects.create_user(username='caixa_preco', password='senha-forte')
    product = ProdutoFactory(nome='Produto protegido', preco_venda='10.00')
    api_client.force_authenticate(user=user)

    response = api_client.patch(
        f'/api/produtos/{product.pk}/preco-pdv/',
        {'preco_venda': '12.50', 'nome': 'Nome indevido'},
        format='json',
    )

    product.refresh_from_db()
    assert response.status_code == 200
    assert product.preco_venda == Decimal('12.50')
    assert product.nome == 'Produto protegido'


@pytest.mark.django_db
def test_producao_nao_pode_alterar_preco_pelo_pdv(api_client):
    user = User.objects.create_user(username='producao_preco', password='senha-forte')
    perfil = user.perfil_bella_fornada
    perfil.papel = PerfilUsuario.Papel.PRODUCAO
    perfil.save(update_fields=['papel', 'updated_at'])
    product = ProdutoFactory(preco_venda='10.00')
    api_client.force_authenticate(user=user)

    response = api_client.patch(
        f'/api/produtos/{product.pk}/preco-pdv/',
        {'preco_venda': '12.50'},
        format='json',
    )

    product.refresh_from_db()
    assert response.status_code == 403
    assert product.preco_venda == Decimal('10.00')


@pytest.mark.django_db
def test_preco_do_pdv_deve_ser_positivo(api_client):
    user = User.objects.create_user(username='caixa_preco_invalido', password='senha-forte')
    product = ProdutoFactory(preco_venda='10.00')
    api_client.force_authenticate(user=user)

    response = api_client.patch(
        f'/api/produtos/{product.pk}/preco-pdv/',
        {'preco_venda': '0.00'},
        format='json',
    )

    product.refresh_from_db()
    assert response.status_code == 400
    assert product.preco_venda == Decimal('10.00')

