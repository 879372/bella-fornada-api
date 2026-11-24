from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command, CommandError

from apps.produtos.balanca_mgv import ErroCargaBalanca, gerar_itensmgv, ler_itensmgv
from apps.produtos.models import ConfiguracaoBalanca, Produto

from apps.produtos.tests.factories import ProdutoFactory


@pytest.mark.django_db
def test_salva_configuracao_da_balanca(auth_client):
    response = auth_client.patch(
        '/api/balancas/configuracao/',
        {
            'modelo': 'Prix 4 Uno',
            'versao_mgv': 'MGV 6',
            'ip': '192.168.1.150',
            'porta': 0,
            'departamento': 1,
            'validade_padrao_dias': 2,
            'prefixo_ean': '2',
        },
        format='json',
    )

    assert response.status_code == 200
    assert response.data['ip'] == '192.168.1.150'
    assert response.data['modelo'] == 'Prix 4 Uno'


COMPLEMENTO = '0' * 16 + '11' + '0' * 64

# Linhas copiadas do ITENSMGV.TXT gerado pelo sistema legado (cp1252, CRLF).
LEGADO = (
    '011000030001200000' + 'TAPIOCA CARNE DE SOL'.ljust(50) + COMPLEMENTO + '\r\n'
    '010000140001399002' + 'PAO KG'.ljust(50) + COMPLEMENTO + '\r\n'
    '010000145003599005' + ' MINI QUEIJADINHA'.ljust(50) + COMPLEMENTO + '\r\n'
    '011000208000500005' + 'BOLO DE LIMÃO'.ljust(50) + COMPLEMENTO + '\r\n'
    '012000279000600000' + 'BAURU REVENDA'.ljust(50) + COMPLEMENTO + '\r\n'
).encode('cp1252')


def test_layout_itensmgv_reproduz_o_arquivo_legado_byte_a_byte():
    itens = ler_itensmgv(LEGADO)

    assert [i.codigo for i in itens] == [30, 140, 145, 208, 279]
    assert itens[1].preco == Decimal('13.99')
    assert itens[1].validade_dias == 2
    assert gerar_itensmgv(itens) == LEGADO
    assert all(len(linha) == 150 for linha in LEGADO.split(b'\r\n') if linha)


@pytest.mark.django_db
def test_exporta_itensmgv_com_produtos_marcados_para_balanca(auth_client):
    ProdutoFactory(codigo_legado=140, nome='Pao kg', preco_venda=Decimal('13.99'),
                   unidade_medida='KG', enviar_balanca=True, validade_balanca_dias=2)
    ProdutoFactory(codigo_legado=30, nome='TAPIOCA CARNE DE SOL', preco_venda=Decimal('12.00'),
                   unidade_medida='UN', enviar_balanca=True, validade_balanca_dias=0)
    ProdutoFactory(codigo_legado=208, nome='Bolo de limão', preco_venda=Decimal('5.00'),
                   unidade_medida='UN', enviar_balanca=True)  # validade padrão
    ProdutoFactory(codigo_legado=279, nome='BAURU REVENDA', preco_venda=Decimal('6.00'),
                   enviar_balanca=True, tipo_balanca='2', validade_balanca_dias=0)
    ProdutoFactory(codigo_legado=145, nome=' MINI QUEIJADINHA', preco_venda=Decimal('35.99'),
                   unidade_medida='KG', enviar_balanca=True)
    ProdutoFactory(codigo_legado=900, unidade_medida='KG', enviar_balanca=False)
    ProdutoFactory(codigo_legado=901, unidade_medida='KG', enviar_balanca=True, ativo=False)
    configuracao = ConfiguracaoBalanca.atual()
    configuracao.validade_padrao_dias = 5
    configuracao.save()

    response = auth_client.get('/api/balancas/exportar/?arquivo=itensmgv')

    assert response.status_code == 200
    assert 'ITENSMGV.TXT' in response['Content-Disposition']
    assert response.content == LEGADO


@pytest.mark.django_db
def test_exporta_depto_no_layout_legado(auth_client):
    response = auth_client.get('/api/balancas/exportar/?arquivo=depto')

    assert response.status_code == 200
    assert 'DEPTO.TXT' in response['Content-Disposition']
    assert response.content == b'01' + b' ' * 40 + b'\r\n'


@pytest.mark.django_db
def test_exportacao_recusa_preco_que_nao_cabe_no_layout(auth_client):
    ProdutoFactory(codigo_legado=1, preco_venda=Decimal('10000.00'), enviar_balanca=True)

    response = auth_client.get('/api/balancas/exportar/')

    assert response.status_code == 400
    assert 'preço' in response.data['detail']


@pytest.mark.django_db
def test_importa_marcacao_da_balanca_do_arquivo_legado(tmp_path):
    arquivo = tmp_path / 'ITENSMGV.TXT'
    arquivo.write_bytes(LEGADO)
    pao = ProdutoFactory(codigo_legado=140, preco_venda=Decimal('12.00'), unidade_medida='KG')
    bauru = ProdutoFactory(codigo_legado=279, preco_venda=Decimal('6.00'))
    antigo = ProdutoFactory(codigo_legado=999, enviar_balanca=True)
    saida = StringIO()

    call_command('importar_carga_balanca', str(arquivo), '--substituir', stdout=saida)

    pao.refresh_from_db()
    bauru.refresh_from_db()
    antigo.refresh_from_db()
    assert (pao.enviar_balanca, pao.tipo_balanca, pao.validade_balanca_dias) == (True, '0', 2)
    assert pao.preco_venda == Decimal('12.00')  # preço não é alterado
    assert (bauru.tipo_balanca, bauru.validade_balanca_dias) == ('2', 0)
    assert antigo.enviar_balanca is False
    assert 'Sem cadastro: código 30' in saida.getvalue()
    assert 'Preço diferente: 140' in saida.getvalue()
    assert Produto.objects.filter(enviar_balanca=True).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize('dry_run', [False, True])
def test_importa_precos_do_txt_e_respeita_dry_run(tmp_path, dry_run):
    arquivo = tmp_path / 'ITENSMGV.TXT'
    arquivo.write_bytes(LEGADO)
    pao = ProdutoFactory(codigo_legado=140, nome='Nome no cadastro', preco_venda=Decimal('12.00'))
    antigo = ProdutoFactory(codigo_legado=999, enviar_balanca=True)
    opcoes = {'dry_run': dry_run, 'atualizar_precos': True, 'substituir': True}
    call_command('importar_carga_balanca', str(arquivo), stdout=StringIO(), **opcoes)
    pao.refresh_from_db()
    antigo.refresh_from_db()
    assert pao.preco_venda == Decimal('12.00' if dry_run else '13.99')
    assert pao.nome == 'Nome no cadastro'
    assert pao.enviar_balanca is (not dry_run)
    assert antigo.enviar_balanca is dry_run
    assert Produto.objects.count() == 2  # não inventa cadastros para códigos ausentes


@pytest.mark.parametrize('conteudo', [
    b'', b'\r\n', LEGADO[:68], LEGADO + LEGADO,
    LEGADO[:2] + b'9' + LEGADO[3:],
    LEGADO[:3] + b'000000' + LEGADO[9:],
])
def test_recusa_arquivo_vazio_truncado_tipo_invalido_ou_codigo_repetido(conteudo):
    with pytest.raises(ErroCargaBalanca):
        ler_itensmgv(conteudo)


@pytest.mark.django_db
def test_importacao_invalida_nao_desmarca_nem_altera_precos(tmp_path):
    arquivo = tmp_path / 'ITENSMGV.TXT'
    arquivo.write_bytes(LEGADO + LEGADO)
    produto = ProdutoFactory(codigo_legado=140, enviar_balanca=True, preco_venda=Decimal('12.00'))
    with pytest.raises(CommandError):
        call_command('importar_carga_balanca', str(arquivo), substituir=True, atualizar_precos=True)
    produto.refresh_from_db()
    assert produto.enviar_balanca is True
    assert produto.preco_venda == Decimal('12.00')


@pytest.mark.django_db
def test_recusa_exportacao_sem_produtos_marcados(auth_client):
    response = auth_client.get('/api/balancas/exportar/')
    assert response.status_code == 400
    assert 'produto ativo' in response.data['detail']


@pytest.mark.django_db
@pytest.mark.parametrize('campo,valor', [('departamento', 100), ('departamento', 0), ('validade_padrao_dias', 1000)])
def test_configuracao_recusa_valores_fora_do_layout(auth_client, campo, valor):
    response = auth_client.patch('/api/balancas/configuracao/', {campo: valor}, format='json')
    assert response.status_code == 400
    assert campo in response.data['message']
