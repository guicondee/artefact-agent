"""Carregamento e divisão (chunking) do manual de políticas, com componentes do LangChain.

Pipeline:
    PDF --PyMuPDF4LLMLoader--> Markdown --limpeza--> MarkdownHeaderTextSplitter --> Documents

O loader converte o PDF em Markdown já com títulos (`#` seção, `##` subseção) e tabelas.
O splitter divide pelos títulos, então cada regra de negócio (ex.: "7 dias para arrependimento")
fica inteira em um único chunk.
"""

import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter

from emporio_agent.config import POLICY_PDF

# Limpeza do Markdown gerado a partir do PDF. O PDF repete cabeçalho/rodapé em toda página e
# mistura tamanhos de fonte nos títulos, então o nível do título é refeito pela NUMERAÇÃO.
_CLEANUPS: list[tuple[str, str]] = [
    (r"^-{3,}\s*$", ""),  # separador de página
    (r"^\*\*Empório da Música\*\* Manual de Políticas e Procedimentos\s*$", ""),  # cabeçalho
    (r"^Página \d+\s*$", ""),  # rodapé
    (r"^#+ \*\*(\d+)\.\s+(.+?)\*\*\s*$", r"# \1. \2"),  # "4. Trocas"      -> seção
    (r"^#+ \*\*(\d+\.\d+)\s+(.+?)\*\*\s*$", r"## \1 \2"),  # "4.1 Arrependimento" -> subseção
    (r"^#+\s+(?!\d)", ""),  # título sem número (capa, slogan) vira texto comum
]


def clean_markdown(markdown: str) -> str:
    for pattern, replacement in _CLEANUPS:
        markdown = re.sub(pattern, replacement, markdown, flags=re.MULTILINE)
    return markdown


def load_policy_chunks(pdf_path: Path = POLICY_PDF) -> list[Document]:
    """Divide o manual em um Document por subseção (ou seção sem subseções).

    O texto de cada chunk começa com o cabeçalho da seção, para que o embedding saiba de que
    assunto o trecho trata. Metadados: section ("4.1"), title e parent (título da seção pai).
    """
    pages = PyMuPDF4LLMLoader(str(pdf_path), mode="single").load()
    splitter = MarkdownHeaderTextSplitter([("#", "secao"), ("##", "subsecao")])

    chunks: list[Document] = []
    for doc in splitter.split_text(clean_markdown(pages[0].page_content)):
        if "secao" not in doc.metadata:  # texto antes da seção 1 (capa)
            continue
        parent_number, parent_title = doc.metadata["secao"].split(" ", 1)
        if "subsecao" in doc.metadata:
            section, title = doc.metadata["subsecao"].split(" ", 1)
            parent = parent_title
        else:
            section, title, parent = parent_number.rstrip("."), parent_title, None

        header = f"Manual de Políticas, seção {section}: {title}"
        if parent:
            header += f' (em "{parent}")'
        chunks.append(
            Document(
                page_content=f"{header}\n{doc.page_content}",
                metadata={"section": section, "title": title, "parent": parent},
            )
        )
    return chunks


if __name__ == "__main__":
    for c in load_policy_chunks():
        print(f"--- [{c.metadata['section']}] ({len(c.page_content)} caracteres)\n{c.page_content}\n")
