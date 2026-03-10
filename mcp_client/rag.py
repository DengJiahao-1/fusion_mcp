from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


def _safe_imports() -> tuple[Any, Any]:
    try:
        import chromadb  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "RAG deps not installed. Install RAG dependencies from requirements.txt."
        ) from exc
    return chromadb, SentenceTransformer


@dataclass
class DocumentChunk:
    text: str
    metadata: Dict[str, Any]


class DocumentLoader:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be in [0, chunk_size)")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _chunk_text(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []
        step = self.chunk_size - self.chunk_overlap
        return [text[i : i + self.chunk_size] for i in range(0, len(text), step)]

    def load_from_file(self, file_path: str) -> List[DocumentChunk]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        chunks = self._chunk_text(content)
        return [
            DocumentChunk(
                text=chunk,
                metadata={"source": file_path, "chunk_index": idx},
            )
            for idx, chunk in enumerate(chunks)
        ]

    def load_from_directory(self, dir_path: str) -> List[DocumentChunk]:
        all_chunks: List[DocumentChunk] = []
        for root, _, files in os.walk(dir_path):
            for name in files:
                file_path = os.path.join(root, name)
                try:
                    all_chunks.extend(self.load_from_file(file_path))
                except Exception:
                    # Skip unreadable or binary files
                    continue
        return all_chunks


class VectorStore:
    def __init__(
        self,
        persist_directory: str,
        collection_name: str,
        embedding_model: str,
    ) -> None:
        chromadb, SentenceTransformer = _safe_imports()
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._embedder = SentenceTransformer(embedding_model)
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(name=collection_name)

    def _embed(self, texts: Iterable[str]) -> List[List[float]]:
        return self._embedder.encode(list(texts), normalize_embeddings=True).tolist()

    def add_documents(self, docs: List[DocumentChunk]) -> int:
        if not docs:
            return 0
        texts = [d.text for d in docs]
        embeddings = self._embed(texts)
        ids = [f"{d.metadata.get('source','doc')}#{d.metadata.get('chunk_index', 0)}" for d in docs]
        metadatas = [d.metadata for d in docs]
        self._collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return len(docs)

    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        embeddings = self._embed([query])
        result = self._collection.query(
            query_embeddings=embeddings,
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        output = []
        for doc, meta, dist in zip(docs, metas, dists):
            output.append({"text": doc, "metadata": meta, "distance": dist})
        return output

    def get_collection_info(self) -> Dict[str, Any]:
        return {
            "name": self.collection_name,
            "count": self._collection.count(),
            "embedding_model": self.embedding_model,
            "persist_directory": self.persist_directory,
        }


class RAGRetriever:
    def __init__(self, vector_store: VectorStore, document_loader: DocumentLoader) -> None:
        self.vector_store = vector_store
        self.document_loader = document_loader

    def add_documents_from_file(self, file_path: str) -> int:
        docs = self.document_loader.load_from_file(file_path)
        return self.vector_store.add_documents(docs)

    def add_documents_from_directory(self, dir_path: str) -> int:
        docs = self.document_loader.load_from_directory(dir_path)
        return self.vector_store.add_documents(docs)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.vector_store.query(query=query, top_k=top_k)

    def format_context(self, results: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for idx, item in enumerate(results, 1):
            source = item.get("metadata", {}).get("source", "unknown")
            lines.append(f"[{idx}] Source: {source}\n{item.get('text', '')}")
        return "\n\n".join(lines)
