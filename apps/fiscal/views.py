from django.db.models import Count, Exists, OuterRef
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from apps.vendas.models import Venda

from .models import DocumentoFiscal
from .serializers import (
    CancelarDocumentoFiscalSerializer,
    DocumentoFiscalSerializer,
    EmitirDocumentoFiscalSerializer,
    EventoFiscalSerializer,
    VendaElegivelFiscalSerializer,
)
from .services.errors import FiscalError
from .services.fiscal import FiscalService


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
        if not user.is_staff:
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
        if not user.is_staff and venda.sessao.operador_id != user.id:
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
        if not request.user.is_staff:
            queryset = queryset.filter(sessao__operador=request.user)

        page = self.paginate_queryset(queryset)
        serializer = VendaElegivelFiscalSerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

