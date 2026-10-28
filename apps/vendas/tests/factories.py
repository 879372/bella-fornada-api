import factory
from apps.vendas.models import Venda, VendaItem, SessaoCaixa
from apps.clientes.tests.factories import ClienteFactory
from apps.produtos.tests.factories import ProdutoFactory
from django.contrib.auth.models import User

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Faker("user_name")
    email = factory.Faker("email")

class SessaoCaixaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SessaoCaixa

    operador = factory.SubFactory(UserFactory)
    fundo_inicial = 100.00
    data_abertura = factory.Faker("date_time_this_month")

class VendaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Venda

    cliente = factory.SubFactory(ClienteFactory)
    sessao = factory.SubFactory(SessaoCaixaFactory)
    total = 0.00
    status = "ABERTA"

class VendaItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VendaItem

    venda = factory.SubFactory(VendaFactory)
    produto = factory.SubFactory(ProdutoFactory)
    quantidade = factory.Faker("pydecimal", left_digits=1, right_digits=1, positive=True, min_value=1)
    preco_unitario = factory.SelfAttribute("produto.preco_venda")
    subtotal = factory.LazyAttribute(lambda o: o.quantidade * o.preco_unitario)
