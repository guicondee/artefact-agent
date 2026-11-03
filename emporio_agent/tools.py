"""Tools que o agente pode invocar (LangChain @tool).

Cada tool é uma função Python decorada com @tool. O LLM vê o nome, a docstring e o schema
dos parâmetros, e decide quando chamá-la. A descrição da tool inclui o schema das views e
exemplos de SQL para guiar o text-to-SQL.

Camadas de proteção (defesa em profundidade):
    1. Banco: a conexão usa o role `agent_ro`, que só tem SELECT nas views permitidas.
    2. Código: valida que o SQL é um único SELECT, injeta LIMIT e aplica statement_timeout.
    3. Pedidos: uma tool separada exige número do pedido + telefone ou e-mail do cliente.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from langchain_core.tools import tool

from emporio_agent.config import database_url
from emporio_agent.rag import search_policies

# ============================================================================ #
#  Constantes para o text-to-SQL
# ============================================================================ #

V_CATALOG_SCHEMA = """\
View shop.v_catalog — catálogo de instrumentos com preço vigente
Colunas:
  product_id         integer       — ID do produto
  name               text          — nome do instrumento (ex.: "Yamaha C40 Nylon Natural")
  category           text          — categoria (Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos, Violões, Ukuleles...)
  description        text          — descrição do produto
  specs              jsonb         — especificações técnicas (chaves variam por categoria)
  list_price_brl     numeric       — preço de tabela em R$
  promo_discount_percent numeric   — percentual de desconto da promoção ativa (NULL se sem promoção)
  promo_name         text          — nome da promoção ativa (NULL se sem promoção)
  promo_price_brl    numeric       — preço com desconto promocional (NULL se sem promoção)
  pix_price_brl      numeric       — preço à vista no PIX com 5% (NULL se há promoção ativa)
  stock_quantity     integer       — unidades em estoque
  status             text          — 'active', 'discontinued' ou 'coming_soon'
  availability       text          — 'in_stock', 'out_of_stock', 'discontinued' ou 'coming_soon'
"""

SQL_EXAMPLES = """\
Exemplos de consultas válidas (dialeto PostgreSQL):
-- Violões disponíveis até R$1000, do mais barato ao mais caro
SELECT name, list_price_brl, promo_price_brl, pix_price_brl, availability
  FROM shop.v_catalog
 WHERE category = 'Violões'
   AND COALESCE(promo_price_brl, list_price_brl) <= 1000
   AND availability = 'in_stock'
 ORDER BY COALESCE(promo_price_brl, list_price_brl);

-- Preço de um produto específico (busca parcial, case-insensitive)
SELECT name, list_price_brl, promo_price_brl, pix_price_brl, promo_name, availability
  FROM shop.v_catalog
 WHERE name ILIKE '%Takamine GD20%';

-- Produtos em promoção
SELECT name, list_price_brl, promo_discount_percent, promo_price_brl, promo_name
  FROM shop.v_catalog
 WHERE promo_price_brl IS NOT NULL;

-- Buscar instrumentos por especificação (jsonb)
SELECT name, list_price_brl, specs->>'color' AS cor
  FROM shop.v_catalog
 WHERE specs->>'color' ILIKE '%sunburst%';
"""

# Segurança no código: só SELECT, sem ponto-e-vírgula extra, limite de linhas.
_MAX_LIMIT = 20
_STATEMENT_TIMEOUT_MS = 5000
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|EXECUTE|SET|RESET)\b",
    re.IGNORECASE,
)


def _safe_execute(sql: str) -> list[dict]:
    """Executa SQL de leitura com guardrails e devolve lista de dicts."""
    sql = sql.strip().rstrip(";")

    if _FORBIDDEN.search(sql):
        raise ValueError("Apenas consultas SELECT são permitidas.")

    if ";" in sql:
        raise ValueError("Apenas um statement por vez é permitido.")

    if not re.match(r"(?i)^\s*SELECT\b", sql):
        raise ValueError("A consulta deve começar com SELECT.")

    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql += f" LIMIT {_MAX_LIMIT}"

    with psycopg.connect(
        database_url(read_only=True),
        options=f"-c statement_timeout={_STATEMENT_TIMEOUT_MS} -c search_path=shop,rag,public",
    ) as conn:
        cur = conn.execute(sql)
        cols = [d.name for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ============================================================================ #
#  Tools
# ============================================================================ #

_CATALOG_DESCRIPTION = f"""\
Consulta o catálogo de instrumentos musicais da loja usando SQL (PostgreSQL).

Use esta tool para responder perguntas sobre produtos: preço, disponibilidade, estoque,
promoções ativas, categorias e especificações técnicas.

{V_CATALOG_SCHEMA}

{SQL_EXAMPLES}

Regras:
- Somente SELECT é permitido.
- Sempre mostre o preço de tabela E o preço promocional (quando houver) na resposta.
- Use ILIKE para buscas por nome (case-insensitive).
- Não invente colunas; use apenas as listadas acima.
"""


@tool(description=_CATALOG_DESCRIPTION)
def consultar_catalogo(sql: str) -> str:
    """Executa uma consulta SQL de leitura no catálogo de instrumentos."""
    try:
        rows = _safe_execute(sql)
    except (ValueError, psycopg.Error) as exc:
        return f"Erro na consulta: {exc}"
    if not rows:
        return "Nenhum resultado encontrado."
    lines = []
    for r in rows:
        lines.append(" | ".join(f"{k}: {v}" for k, v in r.items()))
    return "\n".join(lines)


@tool
def consultar_pedido(order_id: int, phone: str = "", email: str = "") -> str:
    """Consulta o status de um pedido do cliente, com verificação de identidade.

    O cliente deve fornecer o número do pedido E pelo menos um dado de contato (telefone ou
    e-mail cadastrado) para que os dados do pedido sejam exibidos. Isso protege a privacidade
    do cliente (LGPD).

    Retorna: status, data, forma de pagamento, código de rastreamento (se houver) e itens.
    """
    if not phone and not email:
        return "Para consultar um pedido, preciso do número do pedido e do seu telefone ou e-mail cadastrado."

    phone = phone.strip()
    email = email.strip().lower()

    with psycopg.connect(
        database_url(read_only=False),  # precisa ler as tabelas base (customers, orders...)
        options=f"-c statement_timeout={_STATEMENT_TIMEOUT_MS} -c search_path=shop,public",
    ) as conn:
        # Verifica identidade: o pedido existe E pertence a um cliente com esse contato?
        row = conn.execute(
            """
            SELECT o.order_id, o.order_date, o.status, o.total_brl, o.payment_method,
                   o.installments, o.tracking_code, o.estimated_delivery, o.notes,
                   c.name AS customer_name
              FROM orders o
              JOIN customers c ON c.customer_id = o.customer_id
             WHERE o.order_id = %s
               AND (c.phone = %s OR c.email = %s)
            """,
            (order_id, phone, email),
        ).fetchone()

        if not row:
            return (
                "Não encontrei esse pedido com os dados informados. "
                "Verifique o número do pedido e se o telefone ou e-mail é o mesmo do cadastro."
            )

        cols = [
            "order_id", "order_date", "status", "total_brl", "payment_method",
            "installments", "tracking_code", "estimated_delivery", "notes", "customer_name",
        ]
        order = dict(zip(cols, row))

        items = conn.execute(
            """
            SELECT p.name, oi.quantity, p.price_brl
              FROM order_items oi
              JOIN products p ON p.product_id = oi.product_id
             WHERE oi.order_id = %s
            """,
            (order_id,),
        ).fetchall()

    parts = [
        f"Pedido #{order['order_id']} — {order['customer_name']}",
        f"Data: {order['order_date']}",
        f"Status: {order['status']}",
        f"Total: R$ {order['total_brl']}",
        f"Pagamento: {order['payment_method']}" + (f" em {order['installments']}x" if order['installments'] > 1 else ""),
    ]
    if order["tracking_code"]:
        parts.append(f"Rastreamento: {order['tracking_code']}")
    if order["estimated_delivery"]:
        parts.append(f"Previsão de entrega: {order['estimated_delivery']}")
    if order["notes"]:
        parts.append(f"Observações: {order['notes']}")
    if items:
        parts.append("Itens:")
        for name, qty, price in items:
            parts.append(f"  - {qty}x {name} (R$ {price})")
    return "\n".join(parts)


@tool
def buscar_politicas(pergunta: str) -> str:
    """Busca trechos do manual de políticas da loja que respondam à pergunta.

    Use esta tool para perguntas sobre: horário de funcionamento, formas de pagamento,
    parcelamento, trocas e devoluções, frete e entregas, promoções, atendimento, garantia,
    privacidade, dados da empresa (endereço, telefone, CNPJ).

    Retorna os 3 trechos mais relevantes do manual, com a seção de origem.
    """
    results = search_policies(pergunta, k=3)
    if not results:
        return "Não encontrei informações sobre esse assunto no manual de políticas."
    parts = []
    for r in results:
        parts.append(f"[Seção {r['section']} — {r['title']}]\n{r['content']}")
    return "\n\n".join(parts)


@tool
def consultar_horario() -> str:
    """Retorna a data e hora atuais em Campo Grande/MS e se a loja está aberta agora.

    Horário de funcionamento:
    - Segunda a Sexta: 09:00 às 18:00
    - Sábado: 09:00 às 13:00
    - Domingo e Feriados: Fechado
    """
    tz = ZoneInfo("America/Campo_Grande")
    now = datetime.now(tz)
    weekday = now.weekday()  # 0=segunda, 6=domingo

    if weekday <= 4:  # seg a sex
        aberta = 9 <= now.hour < 18
        horario_hoje = "09:00 às 18:00"
    elif weekday == 5:  # sábado
        aberta = 9 <= now.hour < 13
        horario_hoje = "09:00 às 13:00"
    else:  # domingo
        aberta, horario_hoje = False, "Fechado"

    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    status = "ABERTA" if aberta else "FECHADA"
    return (
        f"Agora: {now.strftime('%d/%m/%Y %H:%M')} ({dias[weekday]}-feira) — Fuso: America/Campo_Grande\n"
        f"Horário hoje: {horario_hoje}\n"
        f"Loja: {status}"
    )
