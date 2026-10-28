import factory
from apps.clientes.models import Cliente

class ClienteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cliente

    nome = factory.Faker("name", locale="pt_BR")
    cpf_cnpj = factory.Faker("numerify", text="###########")  # 11 dígitos
    email = factory.Faker("email")
    telefone = factory.Faker("phone_number", locale="pt_BR")
