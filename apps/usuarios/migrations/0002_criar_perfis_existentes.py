from django.db import migrations


def criar_perfis(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    PerfilUsuario = apps.get_model('usuarios', 'PerfilUsuario')
    for user in User.objects.filter(perfil_bella_fornada__isnull=True):
        PerfilUsuario.objects.create(
            usuario=user,
            papel='ADMIN' if user.is_superuser else 'CAIXA',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_perfis, migrations.RunPython.noop),
    ]
