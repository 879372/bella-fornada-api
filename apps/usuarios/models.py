from django.contrib.auth.models import User
from django.db import models

from apps.core.models import BaseModel


class PerfilUsuario(BaseModel):
    class Papel(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        GERENTE = 'GERENTE', 'Gerente'
        CAIXA = 'CAIXA', 'Caixa'
        PRODUCAO = 'PRODUCAO', 'Produção'
        ENTREGADOR = 'ENTREGADOR', 'Entregador'

    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='perfil_bella_fornada',
    )
    papel = models.CharField(max_length=16, choices=Papel.choices, default=Papel.CAIXA)
    telefone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Perfil de usuário'
        verbose_name_plural = 'Perfis de usuários'

    def __str__(self):
        return f'{self.usuario.username} — {self.get_papel_display()}'

