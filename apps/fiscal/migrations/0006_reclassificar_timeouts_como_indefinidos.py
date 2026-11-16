from django.db import migrations
from django.db.models import Q


def reclassificar_timeouts(apps, schema_editor):
    DocumentoFiscal = apps.get_model("fiscal", "DocumentoFiscal")
    EventoFiscal = apps.get_model("fiscal", "EventoFiscal")

    timeout_filter = (
        Q(mensagem_sefaz__icontains="connection timed out")
        | Q(mensagem_sefaz__icontains="erro http: 0")
        | Q(mensagem_sefaz__icontains="tempo limite")
        | Q(mensagem_sefaz__icontains="timeout")
        | Q(mensagem_sefaz__icontains="timed out")
        | Q(mensagem_sefaz__icontains="curl error 28")
    )
    documents = DocumentoFiscal.objects.filter(
        timeout_filter,
        status="REJEITADA",
    )
    for document in documents.iterator():
        DocumentoFiscal.objects.filter(pk=document.pk).update(status="INDEFINIDO")
        EventoFiscal.objects.create(
            documento_id=document.pk,
            tipo="STATUS_ALTERADO",
            status_anterior="REJEITADA",
            status_novo="INDEFINIDO",
            descricao=(
                "Timeout antigo reclassificado como resultado fiscal indefinido."
            ),
        )


class Migration(migrations.Migration):
    dependencies = [("fiscal", "0005_alter_documentofiscal_status_and_more")]

    operations = [
        migrations.RunPython(reclassificar_timeouts, migrations.RunPython.noop),
    ]
