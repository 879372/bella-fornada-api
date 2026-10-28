import re
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from .errors import FiscalConfigurationError, FiscalValidationError


CENT = Decimal("0.01")
FOUR_DECIMALS = Decimal("0.0001")


def only_digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _required_product_value(product, field, label):
    value = getattr(product, field, None)
    if value is None or str(value).strip() == "":
        raise FiscalValidationError(
            f"O produto '{product.nome}' não possui {label} configurado."
        )
    return value


class VendaFiscalPayloadBuilder:
    FORMAS_PAGAMENTO = {
        "DINHEIRO": "01",
        "CARTAO_CREDITO": "03",
        "CARTAO_DEBITO": "04",
        "FIADO": "05",
        "PIX": "17",
    }

    def __init__(self, venda, *, tipo, canal="PDV", ambiente=None, referencia=""):
        self.venda = venda
        self.tipo = tipo
        self.canal = canal
        self.ambiente = ambiente or getattr(settings, "FISCAL_AMBIENTE", "homologacao")
        self.referencia = referencia

    def build(self):
        self._validate_sale()
        cnpj_emitente = only_digits(getattr(settings, "FISCAL_CNPJ_EMITENTE", ""))
        if len(cnpj_emitente) != 14:
            raise FiscalConfigurationError(
                "FISCAL_CNPJ_EMITENTE deve conter um CNPJ válido com 14 dígitos."
            )
        if self.ambiente not in {"homologacao", "producao"}:
            raise FiscalConfigurationError(
                "FISCAL_AMBIENTE deve ser 'homologacao' ou 'producao'."
            )

        items = list(self.venda.itens.select_related("produto").all())
        payload = {
            "cnpj_emitente": cnpj_emitente,
            "itens": self._build_items(items),
            "total": self._document_total(),
            "desconto": Decimal(self.venda.desconto or 0).quantize(CENT),
            "ambiente": self.ambiente,
        }

        if self.tipo == "NFE":
            payload.update(
                {
                    "destinatario": self._build_nfe_recipient(),
                    "natureza_operacao": "Venda de mercadoria",
                    # A referência ajuda a conciliação manual sem enviar o
                    # payload completo ou dados sensíveis para logs locais.
                    "info_adicionais": f"Referência ERP: {self.referencia}"[:200],
                }
            )
        elif self.tipo == "NFCE":
            payload["pagamento"] = self._build_payments()
            payload["presenca"] = "4" if self.canal == "DELIVERY" else "1"
            recipient = self._build_nfce_recipient()
            if recipient:
                payload["destinatario"] = recipient
        else:
            raise FiscalValidationError("Tipo de documento fiscal inválido.")
        return payload

    def _validate_sale(self):
        if self.venda.status != "FINALIZADA":
            raise FiscalValidationError("Somente vendas finalizadas podem emitir documento fiscal.")
        if not self.venda.itens.exists():
            raise FiscalValidationError("A venda não possui itens para emissão fiscal.")
        if self._document_total() <= 0:
            raise FiscalValidationError("O total líquido da venda deve ser maior que zero.")

    def _document_total(self):
        return Decimal(self.venda.total_liquido or 0).quantize(CENT, rounding=ROUND_HALF_UP)

    def _build_items(self, sale_items):
        gross_total = sum((Decimal(item.subtotal) for item in sale_items), Decimal("0"))
        if gross_total <= 0:
            raise FiscalValidationError("Os itens da venda possuem total fiscal inválido.")

        document_total = self._document_total()
        allocated = Decimal("0")
        result = []
        for index, item in enumerate(sale_items):
            product = item.produto
            ncm = only_digits(_required_product_value(product, "ncm", "NCM"))
            cfop = only_digits(_required_product_value(product, "cfop", "CFOP"))
            cst_icms = str(
                _required_product_value(product, "cst_icms", "CST/CSOSN do ICMS")
            ).strip()

            if len(ncm) != 8:
                raise FiscalValidationError(
                    f"O NCM do produto '{product.nome}' deve ter 8 dígitos."
                )
            if len(cfop) != 4:
                raise FiscalValidationError(
                    f"O CFOP do produto '{product.nome}' deve ter 4 dígitos."
                )
            if self.tipo == "NFCE" and cfop not in {"5102", "5405"}:
                raise FiscalValidationError(
                    f"O CFOP do produto '{product.nome}' não é aceito para NFC-e."
                )

            gross_line = Decimal(item.subtotal).quantize(CENT)
            if index == len(sale_items) - 1:
                fiscal_line = document_total - allocated
            else:
                fiscal_line = (document_total * gross_line / gross_total).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                allocated += fiscal_line

            quantity = Decimal(item.quantidade)
            fiscal_unit = (fiscal_line / quantity).quantize(
                FOUR_DECIMALS, rounding=ROUND_HALF_UP
            )
            result.append(
                {
                    "codigo": str(product.codigo_legado or product.pk),
                    "descricao": str(product.nome)[:200],
                    "ncm": ncm,
                    "cfop": cfop,
                    "unidade": str(product.unidade_medida or "UN")[:6],
                    "quantidade": quantity.quantize(FOUR_DECIMALS),
                    "valor_unitario": fiscal_unit,
                    "valor_total": fiscal_line,
                    "desconto": max(gross_line - fiscal_line, Decimal("0")).quantize(CENT),
                    "cst_icms": cst_icms,
                    "aliq_icms": Decimal(getattr(product, "aliquota_icms", 0) or 0),
                    "aliq_pis": Decimal(getattr(product, "aliquota_pis", 0) or 0),
                    "aliq_cofins": Decimal(getattr(product, "aliquota_cofins", 0) or 0),
                }
            )
        return result

    def _build_nfe_recipient(self):
        customer = self.venda.cliente
        if not customer:
            raise FiscalValidationError("NF-e exige um cliente identificado na venda.")

        document = only_digits(customer.cpf_cnpj)
        if len(document) not in {11, 14}:
            raise FiscalValidationError("O cliente da NF-e deve possuir CPF ou CNPJ válido.")

        address_values = {
            "logradouro": (customer.endereco or "").strip(),
            "bairro": (customer.bairro or "").strip(),
            "cidade": (customer.cidade or "").strip(),
            "uf": (customer.uf or "").strip().upper(),
            "cep": only_digits(customer.cep),
        }
        missing = [label for label, value in address_values.items() if not value]
        if missing:
            raise FiscalValidationError(
                "NF-e exige endereço completo do cliente: " + ", ".join(missing) + "."
            )
        if len(address_values["uf"]) != 2 or len(address_values["cep"]) != 8:
            raise FiscalValidationError("UF ou CEP do cliente está inválido para NF-e.")

        name = (customer.razao_social or customer.nome or "").strip()
        if not name:
            raise FiscalValidationError("O cliente da NF-e deve possuir nome ou razão social.")
        recipient = {
            "cpf_cnpj": document,
            "nome": name[:200],
            "endereco": {
                **address_values,
                # O cadastro legado ainda não separa número do logradouro.
                "numero": "SN",
            },
        }
        if customer.email:
            recipient["email"] = customer.email
        return recipient

    def _build_nfce_recipient(self):
        customer = self.venda.cliente
        if not customer:
            return None
        document = only_digits(customer.cpf_cnpj)
        # A implementação atual da ACBRAPI aceita somente CPF no destinatário
        # da NFC-e. Cliente PJ é emitido como consumidor não identificado.
        if len(document) != 11:
            return None
        recipient = {"cpf": document, "nome": (customer.nome or "")[:200]}
        if customer.email:
            recipient["email"] = customer.email
        return recipient

    def _build_payments(self):
        payments = list(self.venda.pagamentos.all())
        if not payments:
            raise FiscalValidationError("NFC-e exige o pagamento registrado na venda.")

        result = []
        for payment in payments:
            code = self.FORMAS_PAGAMENTO.get(payment.forma)
            if not code:
                raise FiscalValidationError(
                    f"A forma de pagamento '{payment.forma}' não possui mapeamento fiscal."
                )
            result.append({"forma": code, "valor": Decimal(payment.valor).quantize(CENT)})

        paid = sum((item["valor"] for item in result), Decimal("0")).quantize(CENT)
        if paid != self._document_total():
            raise FiscalValidationError(
                "Os pagamentos da venda não conferem com o total líquido da NFC-e."
            )
        return result

