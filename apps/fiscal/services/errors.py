class FiscalError(Exception):
    """Erro seguro, próprio para ser apresentado ao operador do PDV."""

    code = "fiscal_error"
    http_status = 400

    def __init__(self, message, *, code=None, http_status=None):
        super().__init__(message)
        self.message = str(message)
        if code:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class FiscalValidationError(FiscalError):
    code = "fiscal_validation_error"
    http_status = 400


class FiscalConfigurationError(FiscalError):
    code = "fiscal_configuration_error"
    http_status = 503


class FiscalConflictError(FiscalError):
    code = "fiscal_conflict"
    http_status = 409


class ACBRAPIError(FiscalError):
    code = "acbr_api_error"
    http_status = 502

    def __init__(
        self,
        message,
        *,
        code=None,
        http_status=None,
        upstream_status=None,
    ):
        super().__init__(message, code=code, http_status=http_status)
        self.upstream_status = upstream_status

