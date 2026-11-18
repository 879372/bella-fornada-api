from decimal import Decimal

from apps.vendas.models import VendaPagamento


def resumo_fechamento(sessao):
    """Conciliação da sessão; consultas relacionadas são pré-carregadas pela view."""
    vendas = list(sessao.venda_set.all())
    finalizadas = [v for v in vendas if v.status == 'FINALIZADA']
    formas = {forma: {'valor': Decimal('0.00'), 'quantidade': 0}
              for forma, _ in VendaPagamento.FORMA_CHOICES}
    for venda in finalizadas:
        usadas = set()
        for pagamento in venda.pagamentos.all():
            formas[pagamento.forma]['valor'] += pagamento.valor
            usadas.add(pagamento.forma)
        for forma in usadas:
            formas[forma]['quantidade'] += 1
    operacoes = list(sessao.operacoes.all())
    sangrias = sum((o.valor for o in operacoes if o.tipo == 'SANGRIA'), Decimal('0.00'))
    suprimentos = sum((o.valor for o in operacoes if o.tipo == 'SUPRIMENTO'), Decimal('0.00'))
    bruto = sum((v.total for v in finalizadas), Decimal('0.00'))
    descontos = sum((v.desconto for v in finalizadas), Decimal('0.00'))
    esperado = sessao.fundo_inicial + formas['DINHEIRO']['valor'] + suprimentos - sangrias
    return {
        'quantidade_vendas': len(finalizadas),
        'quantidade_total': len(vendas),
        'quantidade_abertas': sum(v.status == 'EM_ABERTO' for v in vendas),
        'quantidade_canceladas': sum(v.status == 'CANCELADA' for v in vendas),
        'quantidade_orcamentos': sum(v.status == 'ORCAMENTO' for v in vendas),
        'total_bruto': str(bruto), 'descontos': str(descontos),
        'total_liquido': str(bruto - descontos),
        'ticket_medio': str(((bruto - descontos) / len(finalizadas)).quantize(Decimal('0.01')) if finalizadas else Decimal('0.00')),
        'por_forma': {forma: {'valor': str(item['valor']), 'quantidade': item['quantidade']}
                      for forma, item in formas.items()},
        'total_sangrias': str(sangrias), 'total_suprimentos': str(suprimentos),
        'saldo_esperado': str(esperado),
        'operacoes': [{'id': o.pk, 'tipo': o.tipo, 'valor': str(o.valor),
                       'motivo': o.motivo, 'created_at': o.created_at.isoformat()} for o in operacoes],
    }


def eh_gestao(user):
    if user.is_staff or user.is_superuser:
        return True
    perfil = getattr(user, 'perfil_bella_fornada', None)
    return bool(perfil and perfil.papel in {'ADMIN', 'GERENTE'})


def dados_sessao(sessao, mostrar_conferencia):
    """Fechamento cego: o dinheiro esperado e a diferença só aparecem depois de fechado."""
    resumo = resumo_fechamento(sessao)
    if not mostrar_conferencia:
        resumo['saldo_esperado'] = None
    return {
        'id': sessao.pk, 'operador': sessao.operador_id, 'operador_nome': sessao.operador.username,
        'status': sessao.status, 'aberta_em': sessao.data_abertura,
        'fechada_em': sessao.data_fechamento, 'fundo_inicial': str(sessao.fundo_inicial),
        'valor_contado': str(sessao.valor_contado) if sessao.valor_contado is not None else None,
        'diferenca_caixa': (str(sessao.diferenca_caixa)
                            if mostrar_conferencia and sessao.diferenca_caixa is not None else None),
        'observacoes': sessao.observacoes, 'resumo': resumo,
    }
