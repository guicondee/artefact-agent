"""Configuração central lida do ambiente (.env).

Manter tudo em um único lugar evita ``os.getenv`` espalhado pelo código e
deixa claro quais variáveis o projeto precisa para rodar.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"

# Carrega o .env da raiz do projeto (se existir). Variáveis já exportadas no
# shell têm precedência.
load_dotenv(ROOT_DIR / ".env")


def _get(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name} (veja .env.example)")
    return value


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_model: str
    deepseek_thinking: str  # "enabled" | "disabled"
    google_api_key: str
    embedding_model: str
    pg_user: str
    pg_password: str
    pg_db: str
    pg_host: str
    pg_port: int

    @property
    def pg_dsn(self) -> str:
        """DSN no formato aceito pelo psycopg (sem o prefixo do SQLAlchemy)."""
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


def load_settings() -> Settings:
    return Settings(
        deepseek_api_key=_get("DEEPSEEK_API_KEY"),
        deepseek_model=_get("DEEPSEEK_MODEL", "deepseek-flash"),
        deepseek_thinking=_get("DEEPSEEK_THINKING", "disabled"),
        google_api_key=_get("GOOGLE_API_KEY"),
        embedding_model=_get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        pg_user=_get("POSTGRES_USER", "emporio"),
        pg_password=_get("POSTGRES_PASSWORD", "emporio_dev"),
        pg_db=_get("POSTGRES_DB", "emporio"),
        pg_host=_get("POSTGRES_HOST", "localhost"),
        pg_port=int(_get("POSTGRES_PORT", "5433")),
    )
