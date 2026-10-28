from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.db import connection
from django.db.models import Sum, Avg
from django.utils import timezone
from calendar import monthrange
from datetime import date, timedelta

@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Endpoint para verificação de integridade do sistema (Health Check).
    Verifica se a conexão com o banco de dados está ativa.
    """
    try:
        connection.ensure_connection()
        return Response({
            "status": "ok",
            "database": "connected",
            "message": "Sistema Bella Fornada está online."
        })
    except Exception as e:
        return Response({
            "status": "error",
            "database": "disconnected",
            "error": str(e)
        }, status=503)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """
    Retorna estatísticas consolidadas para o dashboard.
    """
    from apps.vendas.models import Venda
    from apps.produtos.models import EstoqueLoja

    today = timezone.now().date()

    # Recebe filtros de data (formato YYYY-MM-DD)
    data_inicio = request.query_params.get('data_inicio')
    data_fim = request.query_params.get('data_fim')

    if data_inicio:
        start_date = data_inicio
    else:
        start_date = today.replace(day=1)

    if data_fim:
        end_date = data_fim
    else:
        end_date = today

    # 1. KPIs Financeiros
    vendas_hoje = Venda.objects.filter(status='FINALIZADA', created_at__date=today)
    faturamento_hoje = vendas_hoje.aggregate(total=Sum('total'))['total'] or 0
    total_vendas_hoje = vendas_hoje.count()

    vendas_periodo = Venda.objects.filter(status='FINALIZADA', created_at__date__gte=start_date, created_at__date__lte=end_date)
    faturamento_periodo = vendas_periodo.aggregate(total=Sum('total'))['total'] or 0

    # 2. Compras recebidas no período
    from apps.compras.models import NotaCompra
    compras_periodo = NotaCompra.objects.filter(
        status='RECEBIDA',
        data_entrada__gte=start_date,
        data_entrada__lte=end_date
    ).aggregate(total=Sum('valor_total'))['total'] or 0

    # 3. Lucro por Categoria — considera desconto proporcional da venda
    from collections import defaultdict

    vendas_periodo_qs = Venda.objects.filter(
        status='FINALIZADA',
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).prefetch_related('itens__produto')

    lucro_por_grupo: dict = defaultdict(float)

    for venda in vendas_periodo_qs:
        itens = list(venda.itens.all())
        if not itens:
            continue
        total_itens = sum(float(i.preco_unitario) * float(i.quantidade) for i in itens)
        desconto = float(venda.desconto or 0)
        desconto_ratio = desconto / total_itens if total_itens > 0 else 0

        for item in itens:
            if not item.produto:
                continue
            grupo = item.produto.grupo or 'Geral'
            preco_liq = float(item.preco_unitario) * (1 - desconto_ratio)
            lucro_item = (preco_liq - float(item.produto.preco_compra)) * float(item.quantidade)
            lucro_por_grupo[grupo] += lucro_item

    lucro_ranking = sorted(
        [{'name': k, 'total': round(v, 2)} for k, v in lucro_por_grupo.items()],
        key=lambda x: -x['total']
    )

    # 4. Movimento diário do mês selecionado (ou mês atual)
    grafico_vendas = []
    if data_inicio:
        graph_reference = date.fromisoformat(str(data_inicio))
    else:
        graph_reference = today
    graph_start = graph_reference.replace(day=1)
    graph_last_day = monthrange(graph_start.year, graph_start.month)[1]
    graph_end = min(today, graph_start.replace(day=graph_last_day)) if graph_start.month == today.month and graph_start.year == today.year else graph_start.replace(day=graph_last_day)

    for offset in range((graph_end - graph_start).days + 1):
        dia = graph_start + timedelta(days=offset)
        valor_dia = Venda.objects.filter(status='FINALIZADA', created_at__date=dia).aggregate(total=Sum('total'))['total'] or 0
        grafico_vendas.append({
            "data": dia.strftime("%d"),
            "total": float(valor_dia)
        })

    # 5. Alertas de Ruptura (Estoque Baixo)
    produtos_ruptura_qs = EstoqueLoja.objects.filter(quantidade__lte=10).select_related('produto')
    produtos_ruptura = [
        {
            "id": item.produto.id,
            "nome": item.produto.nome,
            "qtd": float(item.quantidade)
        }
        for item in produtos_ruptura_qs[:5]
    ]

    return Response({
        "faturamento_hoje": float(faturamento_hoje),
        "total_vendas_hoje": total_vendas_hoje,
        "faturamento_mes": float(faturamento_periodo),
        "compras_mes": float(compras_periodo),
        "total_descontos": float(vendas_periodo.aggregate(total=Sum('desconto'))['total'] or 0),
        "ticket_medio": float(vendas_periodo.aggregate(media=Avg('total'))['media'] or 0),
        "quantidade_vendas_periodo": vendas_periodo.count(),
        "grafico_vendas": grafico_vendas,
        "lucro_por_categoria": lucro_ranking,
        "produtos_ruptura": produtos_ruptura
    })
