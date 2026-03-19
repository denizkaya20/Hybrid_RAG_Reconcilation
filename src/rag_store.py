"""
rag_store.py
------------
Vector store wrapper for transaction narrative retrieval.

Uses ChromaDB as the persistent vector backend and a SentenceTransformer
model for dense embedding. Designed for multilingual Turkish/English text.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from chromadb import PersistentClient
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from text_norm import normalize_text


class TransactionVectorStore:
    """
    Persistent vector store for bank statement transactions.

    Args:
        persist_dir: Directory where ChromaDB persists its index files.
        embed_model: SentenceTransformer model name or path.
    """

    _COLLECTION_NAME = "transactions"

    def __init__(self, persist_dir: str, embed_model: str) -> None:
        self._client = PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._COLLECTION_NAME
        )
        self._encoder = SentenceTransformer(embed_model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._encoder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if isinstance(embeddings, np.ndarray):
            return embeddings.tolist()
        return embeddings  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Drop and recreate the transaction collection."""
        try:
            self._client.delete_collection(self._COLLECTION_NAME)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=self._COLLECTION_NAME
        )

    def index_transactions(self, transactions: List[Dict]) -> None:
        """
        Embed and store *transactions* in the vector index.

        Args:
            transactions: List of transaction dicts (must contain
                          ``stmt_name``, ``row_id``, ``narrative``, etc.).
        """
        ids, documents, metadata_list = [], [], []

        for txn in transactions:
            doc_id = f"{txn['stmt_name']}|{txn['row_id']}"
            narrative = normalize_text(txn.get("narrative", ""))

            ids.append(doc_id)
            documents.append(narrative)
            metadata_list.append(
                {
                    "stmt_name": txn["stmt_name"],
                    "row_id": int(txn["row_id"]),
                    "date_str": txn.get("date_str", ""),
                    "amount": float(txn.get("amount", 0.0)),
                    "txn_name": txn.get("txn_name", ""),
                }
            )

        embeddings = self._embed(documents)
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadata_list,
            embeddings=embeddings,
        )

    def query(self, query_text: str, top_k: int) -> List[Dict]:
        """
        Retrieve the *top_k* most semantically similar transactions.

        Args:
            query_text: Free-text search query (applicant name, ID, etc.).
            top_k: Maximum number of results to return.

        Returns:
            List of dicts with keys: ``id``, ``distance``, ``narrative``, ``meta``.
        """
        query_normalised = normalize_text(query_text)
        if not query_normalised:
            return []

        query_embedding = self._embed([query_normalised])[0]

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadata_items = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        return [
            {
                "id": ids[i],
                "distance": float(distances[i]) if i < len(distances) else None,
                "narrative": documents[i] if i < len(documents) else "",
                "meta": metadata_items[i] if i < len(metadata_items) else {},
            }
            for i in range(len(ids))
        ]


# ---------------------------------------------------------------------------
# Legacy alias (backward compatibility)
# ---------------------------------------------------------------------------
RagStore = TransactionVectorStore

# Monkey-patch legacy method names so existing code using RagStore still works
TransactionVectorStore.add_txns = TransactionVectorStore.index_transactions  # type: ignore[attr-defined]
