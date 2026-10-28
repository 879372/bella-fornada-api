from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    """
    Handler customizado para retornar erros em um padrão consistente.
    Formato: { "error": true, "message": "...", "status_code": 400 }
    """
    response = exception_handler(exc, context)

    if response is not None:
        custom_data = {
            "error": True,
            "message": response.data,
            "status_code": response.status_code,
        }
        # Se a mensagem for um dicionário de validação, podemos tentar extrair o campo
        if isinstance(response.data, dict):
             # Opcional: aplanar mensagens se necessário
             pass

        response.data = custom_data

    return response
