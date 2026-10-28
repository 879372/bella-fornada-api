import os
import django
import uuid
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
sys.path.append(os.getcwd())
django.setup()

from django.apps import apps

def populate_all_uuids():
    models_to_fix = []
    for app_config in apps.get_app_configs():
        if app_config.name.startswith('apps.'):
            for model in app_config.get_models():
                if hasattr(model, 'id_externo'):
                    models_to_fix.append(model)

    for model in models_to_fix:
        name = model.__name__
        count = 0
        for obj in model.objects.all():
            obj.id_externo = uuid.uuid4()
            obj.save()
            count += 1
        if count > 0:
            print(f"Model {name}: {count} registros atualizados.")

if __name__ == "__main__":
    populate_all_uuids()
