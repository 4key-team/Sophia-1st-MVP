"""MemO: Intelligent Memory with pgvector for semantic search (Task #42597)."""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np

<<<<<<< HEAD
from prometheus_client import Counter, Gauge

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
from app.config import get_settings
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

<<<<<<< HEAD
# Prometheus metrics for MemO
memo_writes_total = Counter(
    'memo_writes_total',
    'Total number of memory write attempts',
    ['status']  # status: success or failure
)

memo_searches_total = Counter(
    'memo_searches_total',
    'Total number of memory search attempts',
    ['status']  # status: success or failure
)

memo_write_success_rate = Gauge(
    'memo_write_success_rate',
    'Memory write success rate (percentage)'
)

memo_search_latency_seconds = Gauge(
    'memo_search_latency_seconds',
    'Memory search latency in seconds',
    ['quantile']  # quantile: avg, p95
)

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

# Memory metrics for monitoring
@dataclass
class MemOMetrics:
    """Metrics for MemO performance tracking"""

    total_searches: int = 0
    total_stores: int = 0
    total_errors: int = 0
    total_hits: int = 0
    avg_search_latency_ms: float = 0.0
    p95_search_latency_ms: float = 0.0
    hit_rate: float = 0.0


class MemOClient:
    """Intelligent memory client with pgvector semantic search"""

    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.MEMO_ENABLED
        self.top_k = self.settings.MEMO_TOP_K
        self.similarity_threshold = self.settings.MEMO_SIMILARITY_THRESHOLD
        self.embedding_model_name = self.settings.MEMO_EMBEDDING_MODEL

        # Performance metrics
        self.metrics = MemOMetrics()
        self._search_latencies: List[float] = []

        # Lazy load embedding model (only if enabled)
        self._embedding_model = None

        if self.enabled:
            logger.info(
                f"MemO enabled: top_k={self.top_k}, threshold={self.similarity_threshold}"
            )
        else:
            logger.info("MemO disabled via MEMO_ENABLED=false")

    def _get_embedding_model(self):
        """Lazy load sentence-transformers model"""
        if self._embedding_model is None and self.enabled:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading embedding model: {self.embedding_model_name}")
                self._embedding_model = SentenceTransformer(self.embedding_model_name)
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self.enabled = False  # Disable if model loading fails
                return None
        return self._embedding_model

<<<<<<< HEAD
    def _parse_vector_from_db(self, vector_str: any) -> Optional[List[float]]:
        """Parse vector from database (handles both string and list formats)"""
        if vector_str is None:
            return None

        # If already a list, return as-is
        if isinstance(vector_str, list):
            return vector_str

        # If it's a string representation, parse it
        if isinstance(vector_str, str):
            try:
                # Remove 'np.str_(' prefix and ')' suffix if present
                if vector_str.startswith("np.str_('") or vector_str.startswith("np.str_(\""):
                    vector_str = vector_str[9:-2]

                # Parse as JSON array
                import json
                return json.loads(vector_str)
            except Exception as e:
                logger.warning(f"Failed to parse vector string: {e}")
                return None

        return None

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector for text"""
        if not self.enabled:
            return None

        try:
            model = self._get_embedding_model()
            if model is None:
                return None

            embedding = model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            self.metrics.total_errors += 1
            return None

    async def store_memory(
        self,
        user_id: str,
        memory_text: str,
        memory_type: str = "context",
        importance: float = 0.5,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> bool:
        """Store a new memory with semantic embedding"""
        if not self.enabled:
            logger.debug("MemO disabled, skipping memory storage")
            return True  # Return success to avoid breaking pipeline

        try:
            start_time = time.perf_counter()

            # Generate embedding
            embedding = self._generate_embedding(memory_text)
            if embedding is None:
                logger.warning("Failed to generate embedding, storing without vector")

            # Prepare memory record
            memory_record = {
                "user_id": user_id,
                "session_id": session_id,
                "memory_text": memory_text,
                "embedding": embedding,
                "memory_type": memory_type,
                "importance": importance,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            # Store in Supabase
            supabase_client = get_supabase(access_token)
            result = (
                supabase_client.table("user_memories").insert(memory_record).execute()
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            self.metrics.total_stores += 1
<<<<<<< HEAD

            # Update Prometheus metrics
            memo_writes_total.labels(status='success').inc()
            self._update_write_success_rate()

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            logger.info(
                f"Memory stored: type={memory_type}, latency={latency_ms:.1f}ms"
            )

            return bool(result.data)

        except Exception as e:
            logger.error(f"Memory storage failed: {e}")
            self.metrics.total_errors += 1
<<<<<<< HEAD

            # Update Prometheus metrics
            memo_writes_total.labels(status='failure').inc()
            self._update_write_success_rate()

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            return False

    async def search_memories(
        self,
        user_id: str,
        query_text: str,
        top_k: Optional[int] = None,
        memory_types: Optional[List[str]] = None,
        access_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for relevant memories using semantic similarity"""
        if not self.enabled:
            logger.debug("MemO disabled, returning empty memories")
            return []

        try:
            start_time = time.perf_counter()

            # Generate query embedding
            query_embedding = self._generate_embedding(query_text)
            if query_embedding is None:
                logger.warning("Failed to generate query embedding")
                self.metrics.total_searches += 1
                return []

            # Search using pgvector cosine similarity
            k = top_k or self.top_k
            supabase_client = get_supabase(access_token)

            # Build query with vector similarity
            # Note: Supabase Python client may not directly support vector operations,
            # so we'll use RPC call to a custom function or direct SQL

            # For now, let's use a simpler approach: fetch recent memories and rank in Python
            # In production, you'd want to use a proper vector search via RPC or direct SQL
            query = (
                supabase_client.table("user_memories")
                .select("*")
                .eq("user_id", user_id)
            )

            if memory_types:
                query = query.in_("memory_type", memory_types)

            # Fetch recent memories (limit to avoid large datasets)
            result = query.order("created_at", desc=True).limit(100).execute()

            if not result.data:
                latency_ms = (time.perf_counter() - start_time) * 1000
                self._record_search_latency(latency_ms)
                self.metrics.total_searches += 1
                logger.debug(f"No memories found for user {user_id}")
                return []

            # Rank by cosine similarity
            memories_with_scores = []
            query_vec = np.array(query_embedding)

<<<<<<< HEAD
            query_norm = float(np.linalg.norm(query_vec))

            for memory in result.data:
                embedding_data = memory.get("embedding")
                if embedding_data:
                    # Parse embedding from database format (pgvector returns string)
                    embedding_list = self._parse_vector_from_db(embedding_data)
                    if embedding_list is None:
                        continue

                    memory_vec = np.array(embedding_list)
                    memory_norm = float(np.linalg.norm(memory_vec))

                    # Skip zero vectors to avoid invalid divisions.
                    if query_norm == 0.0 or memory_norm == 0.0:
                        continue

                    # Cosine similarity
                    similarity = np.dot(query_vec, memory_vec) / (
                        query_norm * memory_norm
=======
            for memory in result.data:
                if memory.get("embedding"):
                    memory_vec = np.array(memory["embedding"])
                    # Cosine similarity
                    similarity = np.dot(query_vec, memory_vec) / (
                        np.linalg.norm(query_vec) * np.linalg.norm(memory_vec)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
                    )

                    if similarity >= self.similarity_threshold:
                        memory["similarity_score"] = float(similarity)
                        memories_with_scores.append(memory)

            # Sort by similarity and take top-k
            memories_with_scores.sort(key=lambda x: x["similarity_score"], reverse=True)
            top_memories = memories_with_scores[:k]

            latency_ms = (time.perf_counter() - start_time) * 1000
            self._record_search_latency(latency_ms)

            self.metrics.total_searches += 1
            if top_memories:
                self.metrics.total_hits += 1

<<<<<<< HEAD
            # Update Prometheus metrics
            memo_searches_total.labels(status='success').inc()

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            logger.info(
                f"Memory search: found={len(top_memories)}/{len(result.data)}, "
                f"latency={latency_ms:.1f}ms, P95={self.metrics.p95_search_latency_ms:.1f}ms"
            )

            return top_memories

        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            self.metrics.total_errors += 1
            self.metrics.total_searches += 1
<<<<<<< HEAD

            # Update Prometheus metrics
            memo_searches_total.labels(status='failure').inc()

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            return []

    def _record_search_latency(self, latency_ms: float):
        """Record search latency for metrics"""
        self._search_latencies.append(latency_ms)

        # Keep last 100 measurements for P95 calculation
        if len(self._search_latencies) > 100:
            self._search_latencies = self._search_latencies[-100:]

        # Update avg and P95
        self.metrics.avg_search_latency_ms = float(np.mean(self._search_latencies))
        self.metrics.p95_search_latency_ms = float(
            np.percentile(self._search_latencies, 95)
        )

        # Update hit rate
        if self.metrics.total_searches > 0:
            self.metrics.hit_rate = (
                self.metrics.total_hits / self.metrics.total_searches
            )

<<<<<<< HEAD
        # Update Prometheus search latency metrics
        memo_search_latency_seconds.labels(quantile='avg').set(
            self.metrics.avg_search_latency_ms / 1000.0
        )
        memo_search_latency_seconds.labels(quantile='p95').set(
            self.metrics.p95_search_latency_ms / 1000.0
        )

    def _update_write_success_rate(self):
        """Update Prometheus write success rate metric"""
        # Get current counter values from Prometheus
        success_count = memo_writes_total.labels(status='success')._value.get()
        failure_count = memo_writes_total.labels(status='failure')._value.get()

        total_writes = success_count + failure_count

        if total_writes > 0:
            success_rate_pct = (success_count / total_writes) * 100.0
            memo_write_success_rate.set(success_rate_pct)
            logger.debug(
                f"Prometheus: memory_write_success_rate = {success_rate_pct:.2f}% "
                f"({success_count}/{total_writes})"
            )

=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    def get_metrics(self) -> Dict[str, Any]:
        """Get current MemO performance metrics"""
        return asdict(self.metrics)

    async def get_context_for_llm(
        self,
        user_id: str,
        current_query: str,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get formatted memory context for LLM prompt composition"""
        if not self.enabled:
            return {"memories": [], "memory_summary": "Memory system disabled"}

        try:
            # Search for relevant memories
            memories = await self.search_memories(
                user_id=user_id,
                query_text=current_query,
                access_token=access_token,
            )

            if not memories:
                return {"memories": [], "memory_summary": "No relevant memories found"}

            # Format memories for prompt
            memory_texts = []
            for mem in memories:
                memory_type = mem.get("memory_type", "context")
                importance = mem.get("importance", 0.5)
                text = mem.get("memory_text", "")
                similarity = mem.get("similarity_score", 0.0)

                memory_texts.append(
                    {
                        "text": text,
                        "type": memory_type,
                        "importance": importance,
                        "relevance": similarity,
                    }
                )

            # Create summary
            summary = f"Retrieved {len(memories)} relevant memories (similarity ≥ {self.similarity_threshold})"

            return {
                "memories": memory_texts,
                "memory_summary": summary,
                "memory_count": len(memories),
            }

        except Exception as e:
            logger.error(f"Failed to get LLM context: {e}")
            return {"memories": [], "memory_summary": "Error retrieving memories"}


# Singleton instance
memo_client = MemOClient()
