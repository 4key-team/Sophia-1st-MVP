"""DeFi FAQ retrieval system using sentence embeddings and cosine similarity."""

import logging
import os
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.services.supabase import get_supabase

# Optional heavy dependency: sentence-transformers (pulls torch, transformers)
# We intentionally avoid installing it in production containers by default.
# If unavailable, RAG gracefully degrades to a no-op that returns empty context.
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # ImportError and others
    SentenceTransformer = None  # type: ignore

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class FAQEntry:
    id: str
    question: str
    answer: str
    category: str
    embedding: Optional[List[float]] = None


@dataclass
class RAGResult:
    question: str
    answer: str
    similarity_score: float
    category: str


class RAGSystem:
    """RAG system for DeFi FAQs with vector search (optional)."""
<<<<<<< HEAD

    def __init__(self):
        self.settings = get_settings()
        self.supabase = get_supabase()
        self.enabled = bool(os.getenv("ENABLE_LOCAL_RAG", "0") == "1") and (
            SentenceTransformer is not None
        )
=======
    
    def __init__(self):
        self.settings = get_settings()
        self.supabase = get_supabase()
        self.enabled = bool(os.getenv("ENABLE_LOCAL_RAG", "0") == "1") and (SentenceTransformer is not None)
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        self._model = None
        self._faqs: List[FAQEntry] = []
        if self.enabled:
            try:
                # Use a lightweight model when enabled
<<<<<<< HEAD
                self._model = SentenceTransformer("all-MiniLM-L6-v2")  # type: ignore
                logger.info("RAGSystem: Local RAG enabled with sentence-transformers")
            except Exception as e:
                logger.warning(
                    f"RAGSystem: Failed to initialize sentence-transformers, disabling RAG ({e})"
                )
                self.enabled = False
        else:
            if SentenceTransformer is None:
                logger.info(
                    "RAGSystem: sentence-transformers not installed; RAG disabled (returns empty context)"
                )
            else:
                logger.info(
                    "RAGSystem: ENABLE_LOCAL_RAG!=1; RAG disabled (returns empty context)"
                )
=======
                self._model = SentenceTransformer('all-MiniLM-L6-v2')  # type: ignore
                logger.info("RAGSystem: Local RAG enabled with sentence-transformers")
            except Exception as e:
                logger.warning(f"RAGSystem: Failed to initialize sentence-transformers, disabling RAG ({e})")
                self.enabled = False
        else:
            if SentenceTransformer is None:
                logger.info("RAGSystem: sentence-transformers not installed; RAG disabled (returns empty context)")
            else:
                logger.info("RAGSystem: ENABLE_LOCAL_RAG!=1; RAG disabled (returns empty context)")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        self._ensure_faqs()
        self.similarity_threshold = 0.7  # Cosine similarity threshold

    @property
    def faqs(self) -> List[FAQEntry]:
        self._ensure_faqs()
        return self._faqs

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")  # Lightweight model

    def _ensure_faqs(self):
        if self._faqs:
            return
        if self.enabled:
            self._load_model()
        self._faqs = self._load_faqs()

    def _load_faqs(self) -> List[FAQEntry]:
        """Load and embed DeFi FAQs (embeddings only when enabled)."""
        faqs_data = self._get_default_faqs()
        faqs = []

        for faq_data in faqs_data:
            embedding = None
            if self.enabled and self._model is not None:
                try:
                    embedding = self._model.encode(faq_data["question"]).tolist()  # type: ignore
                except Exception as e:
<<<<<<< HEAD
                    logger.warning(
                        f"RAGSystem: failed to embed FAQ '{faq_data['id']}': {e}"
                    )

=======
                    logger.warning(f"RAGSystem: failed to embed FAQ '{faq_data['id']}': {e}")
            
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
            faq = FAQEntry(
                id=faq_data["id"],
                question=faq_data["question"],
                answer=faq_data["answer"],
                category=faq_data["category"],
                embedding=embedding,
            )
            faqs.append(faq)
<<<<<<< HEAD

        logger.info(
            f"Loaded {len(faqs)} DeFi FAQs (embeddings={'enabled' if self.enabled else 'disabled'})"
        )
=======
        
        logger.info(f"Loaded {len(faqs)} DeFi FAQs (embeddings={'enabled' if self.enabled else 'disabled'})")
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        return faqs

    def _get_default_faqs(self) -> List[Dict[str, Any]]:
        """Default DeFi FAQ entries"""
        return [
            {
                "id": "faq_001",
                "question": "What is DeFi?",
                "answer": "DeFi (Decentralized Finance) refers to financial services built on blockchain technology that operate without traditional intermediaries like banks.",
                "category": "basics",
            },
            {
                "id": "faq_002",
                "question": "What is yield farming?",
                "answer": "Yield farming involves lending or staking crypto assets in DeFi protocols to earn rewards, often in the form of additional tokens.",
                "category": "yield",
            },
            {
                "id": "faq_003",
                "question": "What is staking?",
                "answer": "Staking involves locking up cryptocurrency to support network operations and earn rewards, typically ranging from 5-20% APY depending on the protocol.",
                "category": "staking",
            },
            {
                "id": "faq_004",
                "question": "What is liquidity providing?",
                "answer": "Liquidity providing means depositing token pairs into automated market makers (AMMs) like Uniswap to earn trading fees and sometimes additional rewards.",
                "category": "liquidity",
            },
            {
                "id": "faq_005",
                "question": "What are the risks of DeFi?",
                "answer": "DeFi risks include smart contract bugs, impermanent loss, market volatility, rugpulls, and regulatory uncertainty. Always do thorough research.",
                "category": "risks",
            },
            {
                "id": "faq_006",
                "question": "What is impermanent loss?",
                "answer": "Impermanent loss occurs when providing liquidity to AMMs and the price ratio of your deposited tokens changes compared to just holding them.",
                "category": "risks",
            },
            {
                "id": "faq_007",
                "question": "What is APY vs APR?",
                "answer": "APY (Annual Percentage Yield) includes compounding effects, while APR (Annual Percentage Rate) is the simple annual rate without compounding.",
                "category": "basics",
            },
            {
                "id": "faq_008",
                "question": "How do I choose a safe DeFi protocol?",
                "answer": "Look for audited smart contracts, high TVL (Total Value Locked), established teams, transparent tokenomics, and strong community backing.",
                "category": "safety",
            },
            {
                "id": "faq_009",
                "question": "What is a DEX?",
                "answer": "A DEX (Decentralized Exchange) allows trading cryptocurrencies directly from your wallet without a central authority, like Uniswap or SushiSwap.",
                "category": "trading",
            },
            {
                "id": "faq_010",
                "question": "What are governance tokens?",
                "answer": "Governance tokens give holders voting rights in protocol decisions, like changing fees, adding new features, or treasury management.",
                "category": "governance",
            },
            {
                "id": "faq_011",
                "question": "What is TVL?",
                "answer": "TVL (Total Value Locked) represents the total dollar value of assets deposited in a DeFi protocol, indicating its popularity and trust level.",
                "category": "metrics",
            },
            {
                "id": "faq_012",
                "question": "What are flash loans?",
                "answer": "Flash loans allow borrowing large amounts of crypto without collateral, as long as you repay within the same blockchain transaction.",
                "category": "advanced",
            },
            {
                "id": "faq_013",
                "question": "What is slippage?",
                "answer": "Slippage is the price difference between when you place a trade and when it executes, often due to price movement during transaction processing.",
                "category": "trading",
            },
            {
                "id": "faq_014",
                "question": "How do gas fees work?",
                "answer": "Gas fees are transaction costs on blockchain networks like Ethereum. They vary based on network congestion and transaction complexity.",
                "category": "technical",
            },
            {
                "id": "faq_015",
                "question": "What is a smart contract?",
                "answer": "Smart contracts are self-executing programs on blockchain that automatically enforce agreements without intermediaries when conditions are met.",
                "category": "technical",
            },
            {
                "id": "faq_016",
                "question": "What are stablecoins?",
                "answer": "Stablecoins are cryptocurrencies designed to maintain stable value, usually pegged to USD, like USDC, USDT, or DAI.",
                "category": "basics",
            },
            {
                "id": "faq_017",
                "question": "What is collateral?",
                "answer": "Collateral is an asset you lock up to secure a loan or position in DeFi, which can be liquidated if the loan isn't repaid.",
                "category": "lending",
            },
            {
                "id": "faq_018",
                "question": "What is a vault strategy?",
                "answer": "Vault strategies are automated DeFi investment approaches that optimize yield farming across multiple protocols to maximize returns.",
                "category": "strategies",
            },
            {
                "id": "faq_019",
                "question": "How do I start with DeFi safely?",
                "answer": "Start with reputable protocols, use small amounts initially, understand the risks, keep private keys secure, and never invest more than you can lose.",
                "category": "safety",
            },
            {
                "id": "faq_020",
                "question": "What is MEV?",
                "answer": "MEV (Maximum Extractable Value) refers to profit opportunities from reordering, including, or censoring transactions within blocks, often through arbitrage or frontrunning.",
                "category": "advanced",
            },
        ]

    def query_faqs(self, query: str, top_k: int = 2) -> List[RAGResult]:
        """Query FAQs using vector similarity search. Returns [] when disabled."""
        if not self.enabled or self._model is None:
            return []
        if not self.faqs:
            logger.warning("No FAQs loaded for RAG query")
            return []

        # Encode the query
        try:
            query_embedding = self._model.encode([query])
        except Exception as e:
            logger.warning(f"RAGSystem: failed to encode query: {e}")
            return []

        # Calculate cosine similarities
        results = []
        for faq in self.faqs:
            if faq.embedding:
                # Calculate cosine similarity
                similarity = np.dot(query_embedding[0], faq.embedding) / (
                    np.linalg.norm(query_embedding[0]) * np.linalg.norm(faq.embedding)
                )

                if similarity >= self.similarity_threshold:
                    results.append(
                        RAGResult(
                            question=faq.question,
                            answer=faq.answer,
                            similarity_score=similarity,
                            category=faq.category,
                        )
                    )

        # Sort by similarity and return top_k
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:top_k]

    def get_context_for_llm(self, query: str) -> str:
        """Get formatted context for LLM from RAG results"""
        rag_results = self.query_faqs(query)

        if not rag_results:
            return ""

        context_parts = []
        for i, result in enumerate(rag_results, 1):
            context_parts.append(
                f"FAQ {i} (similarity: {result.similarity_score:.2f}):\n"
                f"Q: {result.question}\n"
                f"A: {result.answer}"
            )

        return "\n\n".join(context_parts)

    def persist_to_supabase(self):
        """Store FAQs and embeddings in Supabase with pgvector"""
        try:
            # This would create a vector table in Supabase
            # For now, just log that we would do this
            logger.info("Would persist FAQ embeddings to Supabase pgvector table")

            # Example SQL for creating the table:
            # CREATE EXTENSION IF NOT EXISTS vector;
            # CREATE TABLE faq_embeddings (
            #     id TEXT PRIMARY KEY,
            #     question TEXT,
            #     answer TEXT,
            #     category TEXT,
            #     embedding VECTOR(384)
            # );

        except Exception as e:
            logger.error(f"Failed to persist FAQs to Supabase: {e}")


# Singleton instance
rag_system = RAGSystem()
