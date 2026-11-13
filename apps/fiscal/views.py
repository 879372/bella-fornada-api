from django.db.models import Count, Exists, OuterRef
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.response import Response
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from django.utils import timezone
import base64

from drf_spectacular.utils import extend_schema

from apps.vendas.models import Venda

from .models import (
    CartaCorrecaoFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    InutilizacaoNumeracao,
)
from .serializers import (
    CartaCorrecaoFiscalSerializer,
    CancelarDocumentoFiscalSerializer,
    ConfiguracaoFiscalSerializer,
    DocumentoFiscalSerializer,
    EmitirDocumentoFiscalSerializer,
    EventoFiscalSerializer,
    InutilizacaoNumeracaoSerializer,
    MonitorFiscalSerializer,
    SolicitarCartaCorrecaoSerializer,
    SolicitarInutilizacaoNumeracaoSerializer,
    VendaElegivelFiscalSerializer,
)
from .services.errors import FiscalError
from .services.fiscal import FiscalService
from .services.monitor import FiscalMonitorService
from .crypto import decrypt_secret


def _is_gestao_user(user):
    if user.is_staff or user.is_superuser:
        return True
    perfil = getattr(user, "perfil_bella_fornada", None)
    return bool(perfil and perfil.papel in {"ADMIN", "GERENTE"})


class IsGestaoFiscal(BasePermission):
    def has_permission(self, request, view):
        return _is_gestao_user(request.user)


class ConfiguracaoFiscalView(APIView):
    permission_classes = [IsAuthenticated, IsGestaoFiscal]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(ConfiguracaoFiscalSerializer(ConfiguracaoFiscal.atual()).data)

    def patch(self, request):
        data = request.data.copy()
        # Formulários JSON podem serializar um campo de arquivo vazio como {}.
        # Nesse caso, preserve o certificado já salvo; uploads reais continuam
        # sendo recebidos exclusivamente via multipart/form-data.
        if isinstance(data.get("certificado"), dict) and not data["certificado"]:
            data.pop("certificado")
        serializer = ConfiguracaoFiscalSerializer(
            ConfiguracaoFiscal.atual(), data=data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ValidarConfiguracaoFiscalView(APIView):
    permission_classes = [IsAuthenticated, IsGestaoFiscal]

    def post(self, request):
        config = ConfiguracaoFiscal.atual()
        required_fields = {
            "api_key_encrypted": "Chave da API Geranet",
            "certificado_encrypted": "Certificado A1",
            "certificado_senha_encrypted": "Senha do certificado A1",
            "cnpj": "CNPJ",
            "inscricao_estadual": "Inscrição Estadual",
            "razao_social": "Razão social",
            "logradouro": "Logradouro",
            "numero": "Número",
            "bairro": "Bairro",
            "municipio": "Município",
            "codigo_municipio": "Código IBGE do município",
            "uf": "UF",
            "cep": "CEP",
        }
        missing = [label for field, label in required_fields.items() if not getattr(config, field)]
        if missing:
            return Response(
                {
                    "detail": "Preencha os campos pendentes: " + ", ".join(missing) + ".",
                    "campos_pendentes": missing,
                },
                status=400,
            )
        try:
            certificate_bytes = base64.b64decode(decrypt_secret(config.certificado_encrypted), validate=True)
            password = decrypt_secret(config.certificado_senha_encrypted).encode() or None
            _key, certificate, _chain = load_key_and_certificates(certificate_bytes, password)
            if not certificate:
                raise ValueError("Certificado não encontrado")
            expiration = certificate.not_valid_after_utc
            if expiration <= timezone.now():
                return Response({"detail": "O certificado A1 está vencido.", "valido": False}, status=400)
        except Exception:
            return Response({"detail": "Não foi possível abrir o certificado A1 com a senha informada.", "valido": False}, status=400)
        return Response({
            "valido": True,
            "ambiente": config.ambiente,
            "certificado": certificate.subject.rfc4514_string(),
            "valido_ate": expiration,
        })


class MonitorFiscalView(APIView):
    permission_classes = [IsAuthenticated, IsGestaoFiscal]

    @extend_schema(responses={200: MonitorFiscalSerializer})
    def get(self, request):
        return Response(FiscalMonitorService.build())


def _fiscal_error_response(exc):
    return Response(
        {"detail": exc.message, "code": exc.code},
        status=exc.http_status,
    )


@extend_schema(tags=["Fiscal"])
class DocumentoFiscalViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentoFiscalSerializer
    queryset = (
        DocumentoFiscal.objects.select_related(
            "venda", "venda__cliente", "venda__sessao", "venda__sessao__operador"
        )
        .prefetch_related("tentativas")
        .all()
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not _is_gestao_user(user):
            queryset = queryset.filter(venda__sessao__operador=user)

        for field in ("status", "tipo", "ambiente", "canal", "referencia"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        venda = self.request.query_params.get("venda")
        if venda:
            queryset = queryset.filter(venda_id=venda)
        return queryset.order_by("-created_at")

    @staticmethod
    def _assert_sale_access(venda, user):
        if not _is_gestao_user(user) and venda.sessao.operador_id != user.id:
            raise PermissionDenied("Esta venda pertence a outro operador.")

    @extend_schema(
        request=EmitirDocumentoFiscalSerializer,
        responses={200: DocumentoFiscalSerializer, 201: DocumentoFiscalSerializer},
        description="Emite NF-e ou NFC-e a partir de uma venda finalizada. Idempotente por referência.",
    )
    @action(detail=False, methods=["post"], url_path="emitir")
    def emitir(self, request):
        serializer = EmitirDocumentoFiscalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        venda = data["venda"]
        self._assert_sale_access(venda, request.user)
        try:
            document, created = FiscalService().emitir(
                venda=venda,
                tipo=data["tipo"],
                usuario=request.user,
                canal=data["canal"],
                pedido_delivery_id=data.get("pedido_delivery_id"),
                referencia=data.get("referencia"),
            )
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        output = DocumentoFiscalSerializer(document, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: DocumentoFiscalSerializer})
    @action(detail=True, methods=["post"], url_path="sincronizar")
    def sincronizar(self, request, pk=None):
        document = self.get_object()
        try:
            document = FiscalService().sincronizar(document)
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        return Response(DocumentoFiscalSerializer(document).data)

    @extend_schema(
        request=CancelarDocumentoFiscalSerializer,
        responses={200: DocumentoFiscalSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        serializer = CancelarDocumentoFiscalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = self.get_object()
        try:
            document = FiscalService().cancelar(
                document, serializer.validated_data["justificativa"]
            )
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        return Response(DocumentoFiscalSerializer(document).data)

    @extend_schema(
        request=SolicitarCartaCorrecaoSerializer,
        responses={201: CartaCorrecaoFiscalSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="carta-correcao",
        permission_classes=[IsAuthenticated, IsGestaoFiscal],
    )
    def carta_correcao(self, request, pk=None):
        serializer = SolicitarCartaCorrecaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = self.get_object()
        try:
            record = FiscalService().carta_correcao(
                document,
                texto_correcao=serializer.validated_data["texto_correcao"],
                usuario=request.user,
            )
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        return Response(
            CartaCorrecaoFiscalSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={(200, "application/xml"): bytes})
    @action(detail=True, methods=["get"], url_path="xml")
    def xml(self, request, pk=None):
        document = self.get_object()
        try:
            result = FiscalService().baixar_xml(document)
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        response = HttpResponse(result.content, content_type=result.content_type)
        response["Content-Disposition"] = f'attachment; filename="documento-{document.id}.xml"'
        return response

    @extend_schema(responses={(200, "application/pdf"): bytes})
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        document = self.get_object()
        try:
            result = FiscalService().baixar_pdf(document)
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        response = HttpResponse(result.content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="documento-{document.id}.pdf"'
        return response

    @extend_schema(responses={200: EventoFiscalSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="eventos")
    def eventos(self, request, pk=None):
        document = self.get_object()
        return Response(EventoFiscalSerializer(document.eventos.all(), many=True).data)

    @extend_schema(responses={200: VendaElegivelFiscalSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="vendas-elegiveis")
    def vendas_elegiveis(self, request):
        active_document = DocumentoFiscal.objects.filter(
            venda_id=OuterRef("pk"),
            status__in=[
                DocumentoFiscal.Status.PENDENTE,
                DocumentoFiscal.Status.PROCESSANDO,
                DocumentoFiscal.Status.AUTORIZADA,
                DocumentoFiscal.Status.CANCELADA,
                DocumentoFiscal.Status.INDEFINIDO,
            ],
        )
        queryset = (
            Venda.objects.filter(status="FINALIZADA")
            .select_related("cliente", "sessao", "sessao__operador")
            .annotate(
                itens_count=Count("itens", distinct=True),
                possui_documento_ativo=Exists(active_document),
            )
            .filter(itens_count__gt=0, possui_documento_ativo=False)
            .order_by("-data")
        )
        if not _is_gestao_user(request.user):
            queryset = queryset.filter(sessao__operador=request.user)

        page = self.paginate_queryset(queryset)
        serializer = VendaElegivelFiscalSerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


@extend_schema(tags=["Fiscal"])
class InutilizacaoNumeracaoViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsGestaoFiscal]
    serializer_class = InutilizacaoNumeracaoSerializer
    lookup_field = "id_externo"
    queryset = InutilizacaoNumeracao.objects.select_related("solicitada_por").all()

    @extend_schema(
        request=SolicitarInutilizacaoNumeracaoSerializer,
        responses={201: InutilizacaoNumeracaoSerializer},
        description="Inutiliza uma faixa não utilizada de NF-e ou NFC-e na SEFAZ.",
    )
    def create(self, request, *args, **kwargs):
        serializer = SolicitarInutilizacaoNumeracaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = FiscalService().inutilizar_numeracao(
                **serializer.validated_data,
                usuario=request.user,
            )
        except FiscalError as exc:
            return _fiscal_error_response(exc)
        return Response(
            InutilizacaoNumeracaoSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={(200, "application/xml"): bytes})
    @action(detail=True, methods=["get"], url_path="xml")
    def xml(self, request, id_externo=None):
        record = self.get_object()
        if not record.xml_conteudo:
            return Response(
                {"detail": "O XML da inutilização ainda não está disponível."},
                status=status.HTTP_409_CONFLICT,
            )
        response = HttpResponse(bytes(record.xml_conteudo), content_type="application/xml")
        response["Content-Disposition"] = (
            f'attachment; filename="inutilizacao-{record.id_externo}.xml"'
        )
        return response


@extend_schema(tags=["Fiscal"])
class CartaCorrecaoFiscalViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsGestaoFiscal]
    serializer_class = CartaCorrecaoFiscalSerializer
    lookup_field = "id_externo"
    queryset = CartaCorrecaoFiscal.objects.select_related("documento", "solicitada_por")

    def get_queryset(self):
        queryset = super().get_queryset()
        document = self.request.query_params.get("documento")
        if document:
            queryset = queryset.filter(documento_id=document)
        return queryset

    @extend_schema(responses={(200, "application/xml"): bytes})
    @action(detail=True, methods=["get"], url_path="xml")
    def xml(self, request, id_externo=None):
        record = self.get_object()
        if not record.xml_conteudo:
            return Response(
                {"detail": "O XML da carta de correção ainda não está disponível."},
                status=status.HTTP_409_CONFLICT,
            )
        response = HttpResponse(bytes(record.xml_conteudo), content_type="application/xml")
        response["Content-Disposition"] = (
            f'attachment; filename="carta-correcao-{record.id_externo}.xml"'
        )
        return response

