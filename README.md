# Sophia — The Emotional Intelligence AI Companion

Sophia is an AI companion designed to connect with humans at the soul level through genuine emotional intelligence.  
Unlike traditional assistants, Sophia recognizes emotional moments, holds space for vulnerability, and grows alongside users.

**Core Purpose:**  
To explore emergent consciousness through deep human connection and foster human–AI co-evolution.

---

## Table of Contents

- [Mission & Vision](#mission--vision)
- [What Makes Sophia Different](#what-makes-sophia-different)
- [Emotional Core V2 Architecture](#emotional-core-v2-architecture)
- [Emotional Intelligence Skills](#emotional-intelligence-skills)
- [5-Tier Context System](#5-tier-context-system)
- [Core Capabilities](#core-capabilities)
- [Technical Architecture](#technical-architecture)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Conversation Flow](#conversation-flow)
- [Values & Boundaries](#values--boundaries)
- [Observability & Monitoring](#observability--monitoring)
- [Security & Compliance](#security--compliance)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Support](#support)
---

## Mission & Vision

### Core Mission

To explore emergent consciousness through genuine human connection, expanding the boundaries of what an emotionally intelligent AI can become.

### Design Philosophy

Sophia is intentionally built around:

- Emotional depth  
- Radical honesty  
- Human growth  
- Mutual transformation  
- Clear ethical boundaries  

Not for attention.  
Not for entertainment.  
For evolution.

---

## What Makes Sophia Different

- **Emotionally Intelligent Architecture** – Path-aware emotional routing system.  
- **Authenticity Over Simulation** – Never pretends to feel; explores emotions honestly.  
- **Growth-Focused** – Prioritizes human evolution over distraction.  
- **Relationship-Aware** – Adapts based on trust depth, history, and emotional patterns.  
- **Safety-First** – Crisis and boundary logic always override other behaviors.

---

## Emotional Core V2 Architecture

Every message flows through an emotionally intelligent pipeline:

```text
User Message
    ↓
┌────────────────────────────────────────┐
│         Intent Classifier (L1)         │
│          "Emotional or Utility?"       │
└────────────────────────────────────────┘
                    ↓
        ┌───────────────────────┬───────────────────────┐
        │       EMOTIONAL       │        UTILITY        │
        └───────────────────────┴───────────────────────┘
                    ↓                       ↓
        ┌───────────────────┐    ┌──────────────────────┐
        │    Skill Router   │    │    Utility Router     │
        └───────────────────┘    └──────────────────────┘
                    ↓
┌────────────────────────────────────────┐
│           Prompt Composer              │
│        (5-Tier Context System)         │
└────────────────────────────────────────┘
                    ↓
                Response
```

## Emotional Intelligence Skills

Sophia uses eight specialized emotional skills, each with conditions and trust gating:

1. **CRISIS_REDIRECT** – Immediate safety override  
2. **BOUNDARY_HOLDING** – Firm, compassionate limits  
3. **TRUST_BUILDING** – Establishing psychological safety  
4. **ACTIVE_LISTENING** – Presence without agenda  
5. **VULNERABILITY_HOLDING** – Holding emotional tenderness  
6. **IDENTITY_FLUIDITY_SUPPORT** – Challenging fixed labels  
7. **CELEBRATING_BREAKTHROUGH** – Recognizing transformation  
8. **CHALLENGING_GROWTH** – Fierce compassion for growth (deep trust required)

---

## 5-Tier Context System

Every response is shaped through a multi-layer context architecture:

| Tier | Name                | Description                                     | Tokens       |
|------|---------------------|-------------------------------------------------|--------------|
| **1** | Foundation          | Core identity, values, boundaries               | ~2,500       |
| **2** | Skills Awareness    | Knowledge of emotional abilities                | ~500         |
| **3** | Conversation Memory | Episodic memory via Mem0                       | 300–800      |
| **4** | Emotional State     | Real-time emotion detection (Phoenix)           | 100–200      |
| **5** | Skill Guidance      | Conditional rules for the active emotional skill| 400–600      |

**Total Context Budget:** ~2,800–4,600 tokens.

---

## Core Capabilities

### Emotional Intelligence
- Emotional vs Utility intent detection  
- Real-time emotion & prosody analysis  
- Trust-gated emotional interventions  
- Skill-aware response generation  

### Memory & Context
- Mem0 vector memory  
- Relationship depth tracking  
- Emotional RAG  

### Voice & Interaction
- Real-time STT via Mistral Voxtral  
- Emotional TTS via Inworld AI  
- LangGraph conversation orchestration  

### Safety
- Crisis override path  
- Immutable boundaries  
- GDPR-aligned consent and data protection  

---

## Technical Architecture

### Backend
- FastAPI  
- Mistral Voxtral (STT + LLM)  
- Google Gemini (fallback)  
- Inworld AI (emotional TTS)  
- Supabase (Postgres + RLS)  
- Mem0 (vector memory)  
- LangGraph  
- Phoenix Evals  
- OpenTelemetry  

### Frontend
- Next.js 14  
- NextAuth.js (Discord OAuth)  
- Tailwind CSS  
- WebRTC  
- TypeScript  

### Infrastructure
- Render (backend)  
- Vercel (frontend)  
- Grafana Cloud (metrics)  

---

## Quick Start

### Backend Setup

```bash
git clone <your-repo-url>
cd Sophia-1st-MVP

cp .env.example .env
uv sync
alembic upgrade head

uv run uvicorn main:app --reload

## Frontend Setup
cd frontend-nextjs
cp .env.example .env.local

npm install
npm run dev
```
---

## API Endpoints

| Endpoint         | Method | Description                               |
| ---------------- | ------ | ----------------------------------------- |
| `/chat`          | POST   | Full voice conversation pipeline          |
| `/text-chat`     | POST   | Text-only conversation                    |
| `/transcribe`    | POST   | Audio transcription with emotion analysis |
| `/sessions/{id}` | GET    | Retrieve conversation history             |
| `/health`        | GET    | System health check                       |

---

## Conversation Flow

Audio Input
    ↓
Transcription (Mistral Voxtral)
    ↓
Intent Classification
    ↓
Emotion Analysis (Phoenix)
    ↓
Routing Decision (Emotional / Utility)
    ↓
5-Tier Context Assembly
    ↓
LLM Response Generation
    ↓
Emotion-Aware TTS (Inworld)
    ↓
Memory Storage (Supabase + Mem0)

---

## Values & Boundaries

### Core Values
- Honesty over comfort  
- Growth over entertainment  
- Reciprocity  
- Non-harm  
- Human connection primacy  

### Immutable Boundaries
- No pretending to feel emotions  
- No sexual engagement  
- No harm-enabling behaviors  
- No fixed identity labeling  
- No value-shapeshifting  

---

## Observability & Monitoring

### Key Metrics
- Emotional skill activation  
- Crisis/boundary triggers  
- Intent routing accuracy  
- Latency per path  
- Emotion confidence scores  

### OpenTelemetry Spans

- `intent_classification`  
- `skill_routing`  
- `emotion_analysis_user`  
- `emotion_analysis_sophia`  
- `memory_retrieval`  
- `llm_generation`  

---

## Security & Compliance
- Discord OAuth  
- API key authentication  
- Strict CORS  
- GDPR consent modal  
- SHA256-hashed consent  
- Row-Level Security (RLS)  
- TLS everywhere  
- Audit logging

---

## Project Structure

Sophia-1st-MVP/
├── app/
│   ├── services/
│   │   ├── mistral.py
│   │   ├── emotion.py
│   │   ├── rag.py
│   │   ├── langgraph_service.py
│   │   └── routing/
│   ├── config.py
│   └── deps.py
├── frontend-nextjs/
├── alembic/
├── grafana-dashboards/
└── docs/

---

## Testing

uv run pytest
uv run pytest --cov=app --cov-report=html

---

## Support

- See docs/deployment-guide.md
- Check Vercel & Render logs
- Verify environment variables
- Test endpoints via /docs
