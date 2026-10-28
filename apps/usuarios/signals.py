from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilUsuario


@receiver(post_save, sender=User)
def garantir_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.create(
            usuario=instance,
            papel=(
                PerfilUsuario.Papel.ADMIN
                if instance.is_superuser
                else PerfilUsuario.Papel.CAIXA
            ),
        )

