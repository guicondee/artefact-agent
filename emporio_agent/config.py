"""Configuração lida do ambiente (.env), em um único lugar."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_DIR = ROOT / "db"
POLICY_PDF = DATA_DIR / "políticas_da_loja.pdf"

# Variáveis já exportadas no shell têm precedência sobre o .env.
load_dotenv(ROOT / ".env")

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
# Deve coincidir com vector(768) em db/rag.sql. O modelo aceita 768, 1536 ou 3072.
EMBEDDING_DIM = 768


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name} (veja .env.example)")
    return value


def database_url(read_only: bool = False) -> str:
    """DSN do Postgres. `read_only=True` conecta como agent_ro (usado pelo agente)."""
    if read_only:
        user, password = "agent_ro", os.getenv("AGENT_RO_PASSWORD", "agent_ro_dev")
    else:
        user = os.getenv("POSTGRES_USER", "emporio")
        password = os.getenv("POSTGRES_PASSWORD", "emporio_dev")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "emporio")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"
