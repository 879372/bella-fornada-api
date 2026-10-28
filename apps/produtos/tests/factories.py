import factory
from apps.produtos.models import Produto, EstoqueLoja

class ProdutoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Produto

    nome = factory.Faker("word", locale="pt_BR")
    codigo_barras = factory.Faker("numerify", text="#############")
    preco_venda = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    unidade_medida = "UN"
    grupo = factory.Faker("word", locale="pt_BR")
    subgrupo = factory.Faker("word", locale="pt_BR")

class EstoqueLojaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EstoqueLoja

    produto = factory.SubFactory(ProdutoFactory)
    loja = "Loja Principal"
    quantidade = factory.Faker("pydecimal", left_digits=2, right_digits=2, positive=True)
