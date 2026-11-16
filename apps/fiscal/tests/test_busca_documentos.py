import pytest

from apps.fiscal.models import DocumentoFiscal
from apps.vendas.tests.factories import UserFactory, VendaFactory


def make_document(sale, number, key='', status='REJEITADA'):
    return DocumentoFiscal.objects.create(
        venda=sale, tipo='NFCE', ambiente='producao', status=status,
        numero=number, serie='1', chave_acesso=key,
        referencia=f'busca:{sale.pk}:{number}',
    )


@pytest.mark.django_db
def test_search_matches_number_and_formatted_key_beyond_first_page(auth_client):
    sale = VendaFactory(status='FINALIZADA')
    target = make_document(sale, '14056', key='9' * 44)
    for number in range(51):
        make_document(sale, str(number))
    first_page = auth_client.get('/api/fiscal/documentos/')
    assert first_page.data['count'] == 52
    assert str(target.pk) not in [str(row['id']) for row in first_page.data['results']]

    for search in ['14056', '4056', '9' * 44, ' '.join(['9999'] * 11)]:
        response = auth_client.get('/api/fiscal/documentos/', {'q': search})
        assert response.status_code == 200
        assert response.data['count'] == 1
        assert str(response.data['results'][0]['id']) == str(target.pk)
    assert auth_client.get('/api/fiscal/documentos/', {'q': 'inexistente'}).data['count'] == 0
    assert auth_client.get('/api/fiscal/documentos/', {'q': '   '}).data['count'] == 52


@pytest.mark.django_db
def test_search_combines_sale_and_status_and_preserves_operator_permissions(api_client, auth_client):
    user = UserFactory()
    own = VendaFactory(status='FINALIZADA', sessao__operador=user)
    other = VendaFactory(status='FINALIZADA')
    make_document(own, '14056', key='9' * 44)
    make_document(other, '14056', key='8' * 44)
    assert auth_client.get('/api/fiscal/documentos/', {'q': '14056'}).data['count'] == 2
    assert auth_client.get('/api/fiscal/documentos/', {'q': '14056', 'venda': own.pk, 'status': 'REJEITADA'}).data['count'] == 1
    assert auth_client.get('/api/fiscal/documentos/', {'q': '14056', 'status': 'AUTORIZADA'}).data['count'] == 0
    api_client.force_authenticate(user=user)
    assert api_client.get('/api/fiscal/documentos/', {'q': '14056'}).data['count'] == 1
    assert api_client.get('/api/fiscal/documentos/', {'q': '8' * 44}).data['count'] == 0
