import base64
import hashlib
import re
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from apps.fiscal.crypto import decrypt_secret

from .errors import FiscalConfigurationError, FiscalValidationError

CENT = Decimal("0.01")
FOUR = Decimal("0.0001")


def only_digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


class VendaFiscalPayloadBuilder:
    PAYMENT_CODES = {
        "DINHEIRO": "01", "CARTAO_CREDITO": "03", "CARTAO_DEBITO": "04",
        "FIADO": "05", "PIX": "17",
    }

    def __init__(self, venda, *, tipo, canal, configuracao, numero, serie, referencia):
        self.venda = venda
        self.tipo = tipo
        self.canal = canal
        self.config = configuracao
        self.numero = int(numero)
        self.serie = str(serie)
        self.referencia = referencia

    def build(self):
        self._validate()
        now = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
        nfe = {
            "empresa": self._company(),
            "indicadorPresenca": "4" if self.canal == "DELIVERY" else "1",
            "indicativoIntermediador": "0",
            "numeroNotaEmitir": str(self.numero),
            "codigoNumerico": str(int(hashlib.sha256(self.referencia.encode()).hexdigest(), 16) % 100000000).zfill(8),
            "dataSaida": now,
            "dataEmissao": now,
            "modelo": "65" if self.tipo == "NFCE" else "55",
            "ambiente": self._environment(),
            "tipo": "1",
            "frete": "9",
            "finalidade": "1",
            "naturezaOperacao": "Venda de mercadoria",
            "numeroVenda": str(self.venda.pk),
            "pagamento": self._payments(),
            "itens": self._items(),
        }
        recipient = self._recipient(required=self.tipo == "NFE")
        if recipient:
            nfe["cliente"] = recipient
        return {
            "acao": "emitir",
            "modeloDocumento": "nfe",
            "certificadoDigital": self._certificate_hex(),
            "senhaCertificadoDigital": decrypt_secret(self.config.certificado_senha_encrypted),
            "ambiente": self._environment(),
            "modelo": nfe["modelo"],
            "ufEmitente": self.config.uf,
            "nfe": nfe,
        }

    def build_cancellation(self, document, justificativa):
        return {
            "acao": "cancelar", "modeloDocumento": "nfe",
            "chave": document.chave_acesso, "protocolo": document.protocolo,
            "justificativa": justificativa,
            "certificadoDigital": self._certificate_hex(),
            "senhaCertificadoDigital": decrypt_secret(self.config.certificado_senha_encrypted),
            "ambiente": self._environment(),
            "modelo": "65" if document.tipo == "NFCE" else "55",
            "ufEmitente": self.config.uf,
        }

    def _validate(self):
        if self.venda.status != "FINALIZADA" or not self.venda.itens.exists():
            raise FiscalValidationError("Somente vendas finalizadas e com itens podem emitir nota.")
        required = {
            "CNPJ": self.config.cnpj, "inscrição estadual": self.config.inscricao_estadual,
            "razão social": self.config.razao_social, "logradouro": self.config.logradouro,
            "número": self.config.numero, "bairro": self.config.bairro,
            "município": self.config.municipio, "código IBGE": self.config.codigo_municipio,
            "UF": self.config.uf, "CEP": self.config.cep,
        }
        missing = [label for label, value in required.items() if not str(value or "").strip()]
        if missing:
            raise FiscalConfigurationError("Complete a configuração da empresa: " + ", ".join(missing) + ".")
        if len(only_digits(self.config.cnpj)) != 14 or len(only_digits(self.config.codigo_municipio)) != 7:
            raise FiscalConfigurationError("CNPJ ou código IBGE da empresa inválido.")
        if not self.config.api_key_encrypted or not self.config.certificado_encrypted:
            raise FiscalConfigurationError("Configure a chave da Geranet e o certificado A1.")

    def _environment(self):
        return "1" if self.config.ambiente == "producao" else "2"

    def _certificate_hex(self):
        try:
            raw = base64.b64decode(decrypt_secret(self.config.certificado_encrypted), validate=True)
        except Exception as exc:
            raise FiscalConfigurationError("O certificado A1 armazenado é inválido.") from exc
        return raw.hex()

    def _company(self):
        c = self.config
        return {
            "cnpj": only_digits(c.cnpj), "inscricaoEstadual": c.inscricao_estadual,
            "razaoSocial": c.razao_social, "nomeFantasia": c.nome_fantasia,
            "telefone": only_digits(c.telefone), "email": c.email,
            "logradouro": c.logradouro, "numero": c.numero, "complemento": c.complemento,
            "bairro": c.bairro, "municipio": c.municipio,
            "codigoMunicipio": only_digits(c.codigo_municipio), "uf": c.uf,
            "cep": only_digits(c.cep), "codigoRegimeTributario": c.codigo_regime_tributario,
            "tipoAtividade": c.tipo_atividade, "serie": self.serie, "ibptAutomatico": "sim",
        }

    def _items(self):
        sale_items = list(self.venda.itens.select_related("produto"))
        gross_total = sum((_money(i.subtotal) for i in sale_items), Decimal("0"))
        discount_total = _money(self.venda.desconto)
        freight_total = _money(self.venda.taxa_entrega)
        allocated_discount = allocated_freight = Decimal("0")
        result = []
        for index, item in enumerate(sale_items):
            p = item.produto
            ncm, cfop = only_digits(p.ncm), only_digits(p.cfop)
            if len(ncm) != 8 or ncm == "00000000":
                raise FiscalValidationError(f"O produto '{p.nome}' precisa de NCM válido.")
            if len(cfop) != 4:
                raise FiscalValidationError(f"O produto '{p.nome}' precisa de CFOP válido.")
            line = _money(item.subtotal)
            if index == len(sale_items) - 1:
                discount, freight = discount_total - allocated_discount, freight_total - allocated_freight
            else:
                discount = (discount_total * line / gross_total).quantize(CENT)
                freight = (freight_total * line / gross_total).quantize(CENT)
                allocated_discount += discount
                allocated_freight += freight
            barcode = only_digits(p.codigo_barras)
            ean = barcode if len(barcode) in {8, 12, 13, 14} else "SEM GTIN"
            cst = str(p.cst_icms or "").strip()
            if len(cst) not in {2, 3} or not cst.isdigit():
                raise FiscalValidationError(f"O produto '{p.nome}' precisa de CST/CSOSN válido.")
            fiscal_item = {
                "quantidade": Decimal(item.quantidade).quantize(FOUR),
                "valorUnitario": Decimal(item.preco_unitario).quantize(FOUR),
                "valorTotal": line, "desconto": discount, "frete": freight,
                "seguro": Decimal("0.00"), "outro": Decimal("0.00"),
                "ncmProduto": ncm, "cest": only_digits(p.cest), "tipoItem": "00",
                "eanProduto": ean, "codigoProduto": str(p.codigo_legado or p.pk),
                "nomeProduto": p.nome[:120], "cfop": cfop,
                "unidadeMedidaProduto": (p.unidade_medida or "UN").upper()[:6],
                "origemProduto": str(p.origem_mercadoria or "0"),
                "pisCst": str(p.cst_pis or "08"), "pisAliquota": Decimal(p.aliquota_pis or 0),
                "cofinsCst": str(p.cst_cofins or "08"), "cofinsAliquota": Decimal(p.aliquota_cofins or 0),
            }
            regime_simples = self.config.codigo_regime_tributario in {"1", "4"}
            fiscal_item["icmsCsosn" if regime_simples else "icmsCst"] = cst
            if p.codigo_beneficio_fiscal:
                fiscal_item["codigoBeneficioFiscal"] = p.codigo_beneficio_fiscal
            result.append(fiscal_item)
        return result

    def _payments(self):
        payments = list(self.venda.pagamentos.all())
        if not payments:
            raise FiscalValidationError("A venda não possui forma de pagamento fiscal.")
        details = []
        for payment in payments:
            details.append({
                "tipoPagamento": self.PAYMENT_CODES.get(payment.forma, "99"),
                "valorPagamento": _money(payment.valor),
                "indicadorPagamento": "1" if payment.forma == "FIADO" else "0",
            })
        paid = sum((item["valorPagamento"] for item in details), Decimal("0"))
        return {"troco": max(paid - _money(self.venda.total_liquido), Decimal("0")), "detalhamento": details}

    def _recipient(self, *, required):
        client = self.venda.cliente
        if not client:
            if required:
                raise FiscalValidationError("Selecione um cliente para emitir NF-e.")
            return None
        document = only_digits(client.cpf_cnpj)
        if len(document) not in {11, 14}:
            if required:
                raise FiscalValidationError("O CPF/CNPJ do cliente é inválido.")
            return None
        recipient = {
            "razaoSocial": client.razao_social or client.nome,
            "consumidorFinal": "1", "indicadorIEdestinatario": "1" if client.inscricao_estadual else "9",
            "inscricaoEstadual": client.inscricao_estadual or "",
            "telefone": only_digits(client.telefone), "email": client.email or "",
        }
        recipient["cnpj" if len(document) == 14 else "cpf"] = document
        address = {
            "logradouro": client.endereco, "numero": client.numero,
            "complemento": client.complemento, "bairro": client.bairro,
            "municipio": client.cidade, "codigoMunicipio": only_digits(client.codigo_municipio),
            "uf": (client.uf or "").upper(), "cep": only_digits(client.cep),
            "codigoPais": "1058", "nomePais": "BRASIL",
        }
        if required:
            missing = [key for key in ("logradouro", "numero", "bairro", "municipio", "codigoMunicipio", "uf", "cep") if not address[key]]
            if missing or len(address["codigoMunicipio"]) != 7:
                raise FiscalValidationError("Complete o endereço e o código IBGE do cliente para emitir NF-e.")
        if address["logradouro"]:
            recipient.update(address)
        return recipient
