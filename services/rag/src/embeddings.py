"""
embeddings.py — Local Embedding Model Service using FastEmbed (bge-small-en-v1.5).

Produces deterministic, L2-normalized 384-dimensional vector embeddings on CPU.
"""

from __future__ import annotations

import logging
from typing import List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Local embedding generation service using FastEmbed BAAI/bge-small-en-v1.5.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    DIMENSION = 384

    def __init__(self, model_name: str = DEFAULT_MODEL, normalize: bool = True):
        self.model_name = model_name
        self.normalize = normalize
        self._model = None
        self._initialize_model()

    def _initialize_model(self):
        """Initializes FastEmbed TextEmbedding engine."""
        try:
            from fastembed import TextEmbedding
            logger.info("Initializing FastEmbed TextEmbedding model '%s'...", self.model_name)
            self._model = TextEmbedding(model_name=self.model_name)
            logger.info("FastEmbed model initialized successfully.")
        except Exception as exc:
            logger.error("Failed to initialize FastEmbed model %s: %s", self.model_name, exc)
            self._model = None

    @property
    def is_available(self) -> bool:
        """Checks if the embedding model is successfully loaded."""
        return self._model is not None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generates vector embeddings for a batch of text strings.
        Returns a list of 384-dimensional float vectors.
        """
        if not texts:
            return []

        if not self._model:
            raise RuntimeError(
                f"Embedding model '{self.model_name}' is not initialized. "
                "Ensure fastembed is installed and models are downloaded."
            )

        # Clean strings
        safe_texts = [t.strip() if t and t.strip() else "empty passage" for t in texts]

        # Generate embeddings via FastEmbed generator
        raw_embeddings = list(self._model.embed(safe_texts))

        results: List[List[float]] = []
        for emb in raw_embeddings:
            vec = np.array(emb, dtype=np.float32)
            if self.normalize:
                norm = np.linalg.norm(vec)
                if norm > 1e-12:
                    vec = vec / norm
            results.append(vec.tolist())

        return results

    def embed_query(self, query: str) -> List[float]:
        """Generates embedding for a single search query."""
        results = self.embed_texts([query])
        return results[0] if results else [0.0] * self.DIMENSION


# Singleton instance
_default_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Returns singleton EmbeddingService instance."""
    global _default_embedding_service
    if _default_embedding_service is None:
        _default_embedding_service = EmbeddingService()
    return _default_embedding_service

