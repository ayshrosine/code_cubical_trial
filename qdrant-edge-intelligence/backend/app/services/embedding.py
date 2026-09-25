"""
Text embedding service with hybrid local/API approach.

Provides flexible text-to-vector conversion:
- Local sentence-transformers (fully offline, no API calls)
- API-based fallback (OpenAI/similar) when local unavailable
- Automatic fallback logic for resilience
"""
import os
import time
from typing import List, Optional

from app.config import VECTOR_SIZE


class EmbeddingService:
    def __init__(self):
        self._local_model = None
        self._api_client = None
        self._use_local = True
        self._initialize_local()
        self._initialize_api()

    def _initialize_local(self):
        """Initialize local sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer
            # Use all-MiniLM-L6-v2 (384-dim, fast, good quality)
            model_name = "sentence-transformers/all-MiniLM-L6-v2"
            self._local_model = SentenceTransformer(model_name)
            print(f"EmbeddingService: Local model loaded: {model_name}")
        except ImportError:
            print("EmbeddingService: sentence-transformers not installed, skipping local model")
            self._use_local = False
        except Exception as e:
            print(f"EmbeddingService: Failed to load local model: {e}")
            self._use_local = False

    def _initialize_api(self):
        """Initialize API-based embedding client."""
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                import openai
                self._api_client = openai.OpenAI(api_key=api_key)
                print("EmbeddingService: API client initialized")
            except ImportError:
                print("EmbeddingService: openai package not installed")
            except Exception as e:
                print(f"EmbeddingService: Failed to initialize API client: {e}")

    def embed(self, text: str, prefer_local: bool = True) -> List[float]:
        """
        Convert text to vector embedding.

        Args:
            text: Input text to embed
            prefer_local: Try local model first (default True)

        Returns:
            List of floats representing the embedding vector

        Raises:
            ValueError: If both local and API embedding fail
        """
        if prefer_local and self._use_local and self._local_model:
            try:
                return self._embed_local(text)
            except Exception as e:
                print(f"EmbeddingService: Local embedding failed: {e}, trying API fallback")

        if self._api_client:
            try:
                return self._embed_api(text)
            except Exception as e:
                print(f"EmbeddingService: API embedding failed: {e}")

        raise ValueError("EmbeddingService: No available embedding method")

    def _embed_local(self, text: str) -> List[float]:
        """Embed using local sentence-transformers model."""
        start_time = time.time()
        embedding = self._local_model.encode(text, convert_to_numpy=True)
        elapsed = time.time() - start_time
        print(f"EmbeddingService: Local embedding took {elapsed:.3f}s")
        return embedding.tolist()

    def _embed_api(self, text: str) -> List[float]:
        """Embed using OpenAI API (text-embedding-3-small)."""
        start_time = time.time()
        response = self._api_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=VECTOR_SIZE
        )
        elapsed = time.time() - start_time
        print(f"EmbeddingService: API embedding took {elapsed:.3f}s")
        return response.data[0].embedding

    def embed_batch(self, texts: List[str], prefer_local: bool = True) -> List[List[float]]:
        """
        Embed multiple texts efficiently.

        Args:
            texts: List of input texts
            prefer_local: Try local model first (default True)

        Returns:
            List of embedding vectors
        """
        if prefer_local and self._use_local and self._local_model:
            try:
                start_time = time.time()
                embeddings = self._local_model.encode(texts, convert_to_numpy=True)
                elapsed = time.time() - start_time
                print(f"EmbeddingService: Local batch embedding ({len(texts)} texts) took {elapsed:.3f}s")
                return embeddings.tolist()
            except Exception as e:
                print(f"EmbeddingService: Local batch embedding failed: {e}, falling back to individual API calls")

        # Fallback to individual API calls
        return [self.embed(text, prefer_local=False) for text in texts]

    def is_local_available(self) -> bool:
        """Check if local embedding is available."""
        return self._use_local and self._local_model is not None

    def is_api_available(self) -> bool:
        """Check if API embedding is available."""
        return self._api_client is not None


# Global instance
embedding_service = EmbeddingService()
