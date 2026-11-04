-- Schema "memory": histórico das conversas (checkpoints do LangGraph).
-- As tabelas (checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations)
-- são criadas pelo PostgresSaver.setup(), com a conexão em search_path=memory.
-- Sem DROP: o histórico precisa sobreviver a reinícios da CLI.
-- O role agent_ro não recebe acesso. O histórico pode conter dados pessoais (LGPD).

CREATE SCHEMA IF NOT EXISTS memory;

REVOKE ALL ON SCHEMA memory FROM PUBLIC;
