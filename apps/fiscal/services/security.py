import re


_API_KEY_RE = re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_.-]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{11,}(?!\d)")


def sanitize_text(value, *, max_length=500):
    """Remove segredos e identificadores pessoais de mensagens persistidas/logadas."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = _API_KEY_RE.sub("[CHAVE_REMOVIDA]", text)
    text = _BEARER_RE.sub("Bearer [TOKEN_REMOVIDO]", text)
    text = _EMAIL_RE.sub("[EMAIL_REMOVIDO]", text)
    text = _LONG_DIGITS_RE.sub("[DOCUMENTO_REMOVIDO]", text)
    text = re.sub(r"\s+", " ", text)
    return text[:max_length]


def extract_safe_error(data, *, fallback="Falha na comunicação com a ACBRAPI."):
    """Extrai somente uma mensagem curta; nunca serializa o payload completo."""
    if isinstance(data, dict):
        for key in ("detail", "mensagem", "message", "motivo_status", "erro"):
            value = data.get(key)
            if value:
                return sanitize_text(value)

        autorizacao = data.get("autorizacao")
        if isinstance(autorizacao, dict):
            message = autorizacao.get("motivo_status") or autorizacao.get("message")
            if message:
                return sanitize_text(message)

        errors = data.get("erros") or data.get("errors")
        if errors:
            return extract_safe_error(errors, fallback=fallback)

        # Erros de validação do DRF normalmente são {campo: [mensagem]}.
        for field, value in data.items():
            if isinstance(value, (list, tuple)) and value:
                return sanitize_text(f"{field}: {value[0]}")
            if isinstance(value, str):
                return sanitize_text(f"{field}: {value}")

    if isinstance(data, (list, tuple)) and data:
        return extract_safe_error(data[0], fallback=fallback)
    if isinstance(data, str) and data:
        return sanitize_text(data)
    return fallback

