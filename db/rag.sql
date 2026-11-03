-- Schema "rag": guarda os embeddings das políticas.
-- As tabelas em si (langchain_pg_collection e langchain_pg_embedding) são criadas pelo
-- PGVector do LangChain durante a indexação, dentro deste schema (ver emporio_agent/rag.py).
-- Recriado a cada `python -m emporio_agent.rag index`.
-- Pré-requisitos: extensão vector (docker/initdb) e role agent_ro (emporio_agent.load_data).

DROP SCHEMA IF EXISTS rag CASCADE;
CREATE SCHEMA rag;

-- O agente (agent_ro) só lê. As tabelas ainda não existem, então a permissão é por padrão.
REVOKE ALL ON SCHEMA rag FROM PUBLIC;
GRANT USAGE ON SCHEMA rag TO agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT ON TABLES TO agent_ro;

-- Sem índice vetorial de propósito: com ~25 trechos a busca exata é instantânea, e um índice
-- aproximado (HNSW/IVFFlat) só adicionaria imprecisão. Revisitar se o volume crescer muito.
