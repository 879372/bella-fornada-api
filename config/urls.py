from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from apps.core.views import dashboard_stats

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth JWT
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Dashboard
    path('api/dashboard-stats/', dashboard_stats, name='dashboard-stats'),

    # Documentação Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # APIs
    path('api/', include('apps.core.urls')),
    path('api/', include('apps.produtos.urls')),
    path('api/', include('apps.clientes.urls')),
    path('api/', include('apps.vendas.urls')),
    path('api/financeiro/', include('apps.financeiro.urls')),
    path('api/', include('apps.compras.urls')),
]
