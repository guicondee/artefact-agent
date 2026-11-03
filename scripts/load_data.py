"""Carrega os CSVs de data/ no Postgres (schema "shop").

Uso (com o banco no ar via `docker compose up -d`):
    python scripts/load_data.py

Passos, tudo em uma única transação (ou carrega tudo, ou nada):
    1. recria o schema (db/schema.sql)
    2. limpa e insere os dados dos CSVs
    3. cria o role somente leitura agent_ro
    4. cria as views e concede permissões (db/views.sql)
"""

import csv
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_DIR = ROOT / "db"

load_dotenv(ROOT / ".env")


def get_dsn() -> str:
    user = os.getenv("POSTGRES_USER", "emporio")
    password = os.getenv("POSTGRES_PASSWORD", "emporio_dev")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "emporio")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# --------------------------------------------------------------------------- #
# Leitura e limpeza
# --------------------------------------------------------------------------- #
def read_csv(name: str) -> list[dict[str, str]]:
    """Lê um CSV como lista de dicts, com espaços das pontas removidos."""
    with open(DATA_DIR / f"{name}.csv", encoding="utf-8-sig", newline="") as f:
        return [{k: v.strip() for k, v in row.items()} for row in csv.DictReader(f)]


def opt(value: str) -> str | None:
    """Campo vazio no CSV vira NULL no banco."""
    return value or None


def opt_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def split_payment(raw: str) -> tuple[str, int]:
    """'credit_12x' -> ('credit', 12); 'pix' -> ('pix', 1)."""
    method, _, parcelas = raw.partition("_")
    return method, int(parcelas.rstrip("x")) if parcelas else 1


def load_all(conn: psycopg.Connection) -> dict[str, int]:
    """Insere os CSVs respeitando a ordem das chaves estrangeiras."""
    counts: dict[str, int] = {}

    def insert(table: str, columns: list[str], rows: list[tuple]) -> None:
        query = sql.SQL("INSERT INTO shop.{} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() * len(columns)),
        )
        with conn.cursor() as cur:
            cur.executemany(query, rows)
        counts[table] = len(rows)

    insert(
        "categories",
        ["category_id", "name", "description"],
        [(int(r["category_id"]), r["name"], opt(r["description"])) for r in read_csv("categories")],
    )
    insert(
        "products",
        ["product_id", "category_id", "name", "description", "price_brl",
         "stock_quantity", "status", "specs", "created_at"],
        [
            (int(r["product_id"]), int(r["category_id"]), r["name"], opt(r["description"]),
             Decimal(r["price_brl"]), int(r["stock_quantity"]), r["status"],
             Jsonb(json.loads(r["specs"] or "{}")), date.fromisoformat(r["created_at"]))
            for r in read_csv("products")
        ],
    )
    insert(
        "customers",
        ["customer_id", "name", "phone", "email", "city"],
        [
            (int(r["customer_id"]), r["name"], r["phone"], r["email"].lower(), r["city"])
            for r in read_csv("customers")
        ],
    )
    order_rows = []
    for r in read_csv("orders"):
        method, installments = split_payment(r["payment_method"])
        order_rows.append(
            (int(r["order_id"]), int(r["customer_id"]), date.fromisoformat(r["order_date"]),
             r["status"], Decimal(r["total_brl"]), method, installments,
             opt(r["tracking_code"]), opt_date(r["estimated_delivery"]), opt(r["notes"]))
        )
    insert(
        "orders",
        ["order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
         "installments", "tracking_code", "estimated_delivery", "notes"],
        order_rows,
    )
    insert(
        "order_items",
        ["order_id", "product_id", "quantity"],
        [(int(r["order_id"]), int(r["product_id"]), int(r["quantity"])) for r in read_csv("order_items")],
    )
    insert(
        "promotions",
        ["promotion_id", "product_id", "discount_percent", "description", "is_active"],
        [
            (int(r["promotion_id"]), int(r["product_id"]), Decimal(r["discount_percent"]),
             r["description"], r["is_active"] == "1")
            for r in read_csv("promotions")
        ],
    )
    return counts


def ensure_readonly_role(conn: psycopg.Connection) -> None:
    """Cria (se não existir) o role usado pelo agente. Roles são globais no cluster."""
    password = os.getenv("AGENT_RO_PASSWORD", "agent_ro_dev")
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'agent_ro'").fetchone()
    if not exists:
        conn.execute(sql.SQL("CREATE ROLE agent_ro LOGIN PASSWORD {}").format(sql.Literal(password)))


def main() -> None:
    with psycopg.connect(get_dsn()) as conn:  # commit ao sair; rollback em caso de erro
        conn.execute((DB_DIR / "schema.sql").read_text(encoding="utf-8"))
        counts = load_all(conn)
        ensure_readonly_role(conn)
        conn.execute((DB_DIR / "views.sql").read_text(encoding="utf-8"))
    for table, n in counts.items():
        print(f"shop.{table:<12} {n:>3} linhas")
    print("OK: schema, dados, views e role agent_ro prontos.")


if __name__ == "__main__":
    main()
