from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BairroEntregaViewSet,
    ComplementoViewSet,
    ConfiguracaoDeliveryView,
    EntregadorViewSet,
    GrupoComplementoViewSet,
    PedidoInternoViewSet,
    ProdutoGrupoComplementoViewSet,
    PublicMenuView,
    PublicOrderCreateView,
    PublicOrderTrackingView,
)


router = DefaultRouter()
router.register(r"delivery/bairros", BairroEntregaViewSet, basename="delivery-bairro")
router.register(
    r"delivery/grupos-complementos",
    GrupoComplementoViewSet,
    basename="delivery-grupo-complemento",
)
router.register(
    r"delivery/complementos", ComplementoViewSet, basename="delivery-complemento"
)
router.register(
    r"delivery/vinculos-complementos",
    ProdutoGrupoComplementoViewSet,
    basename="delivery-vinculo-complemento",
)
router.register(
    r"delivery/entregadores", EntregadorViewSet, basename="delivery-entregador"
)
router.register(
    r"delivery/pedidos", PedidoInternoViewSet, basename="delivery-pedido-interno"
)


urlpatterns = [
    # Contrato público principal, compatível com a vitrine web.
    path(
        "public/<slug:slug>/menu/",
        PublicMenuView.as_view(),
        name="delivery-public-menu-slug",
    ),
    path(
        "public/<slug:slug>/orders/",
        PublicOrderCreateView.as_view(),
        name="delivery-public-order-create-slug",
    ),
    path(
        "public/orders/<uuid:token>/",
        PublicOrderTrackingView.as_view(),
        name="delivery-public-tracking",
    ),
    # Atalhos para instalações single-store e compatibilidade do frontend.
    path("delivery/menu/", PublicMenuView.as_view(), name="delivery-public-menu"),
    path(
        "delivery/pedidos/rastrear/<uuid:token>/",
        PublicOrderTrackingView.as_view(),
        name="delivery-public-tracking-alias",
    ),
    path(
        "delivery/configuracao/",
        ConfiguracaoDeliveryView.as_view(),
        name="delivery-configuracao",
    ),
] + router.urls

