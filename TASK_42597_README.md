# Task #42597: MemO Memory - Quick Start Guide

## Overview
MemO (Memory Optimization) - интеллектуальная система памяти с использованием pgvector для семантического поиска релевантных воспоминаний пользователя.

## Компоненты

### 1. MemO Client (`app/services/memo.py`)
Клиент для работы с векторной базой данных воспоминаний:
- Хранение воспоминаний с embeddings
- Семантический поиск (cosine similarity)
- Метрики производительности (P95 latency, hit-rate, errors)

### 2. PromptComposer (`app/services/prompt_composer.py`)
Система композиции промптов:
- Загрузка базовой идентичности из `prompts/base_identity.md`
- Добавление контекста памяти
- Адаптация под эмоции пользователя
- Hot reload промптов

### 3. Database Migration (`alembic/versions/202502110002_add_user_memories_pgvector.py`)
Миграция для создания таблицы `user_memories` с pgvector поддержкой.

## Environment Variables

```env
# MemO Configuration
MEMO_ENABLED=true                                              # Enable/disable memory system
MEMO_TOP_K=5                                                  # Number of memories to retrieve
MEMO_SIMILARITY_THRESHOLD=0.7                                 # Minimum cosine similarity
MEMO_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2  # Embedding model
```

## Setup

### 1. Install Dependencies
```bash
pip install sentence-transformers
# Or regenerate requirements.txt
uv pip compile requirements.in -o requirements.txt
pip install -r requirements.txt
```

### 2. Run Database Migration
```bash
alembic upgrade head
```

### 3. Create Base Identity
Файл `prompts/base_identity.md` уже создан с базовой идентичностью Софии.

## API Endpoints

### POST /admin/reload-prompts
Горячая перезагрузка системных промптов.

**Request:**
```bash
curl -X POST http://localhost:8000/admin/reload-prompts \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
{
  "message": "Prompts reloaded successfully",
  "status": {
    "last_reload": "2025-02-11T10:30:00",
    "base_identity_loaded": true,
    "file_exists": true,
    "file_size": 1234
  },
  "timestamp": 1707649800.0
}
```

### GET /admin/memo-metrics
Получить метрики производительности MemO.

**Request:**
```bash
curl http://localhost:8000/admin/memo-metrics \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
{
  "memo_enabled": true,
  "metrics": {
    "total_searches": 150,
    "total_stores": 200,
    "total_errors": 2,
    "total_hits": 120,
    "avg_search_latency_ms": 45.3,
    "p95_search_latency_ms": 58.7,
    "hit_rate": 0.80
  },
  "timestamp": 1707649800.0
}
```

## Usage Example

### Storing Memories
```python
from app.services.memo import memo_client

await memo_client.store_memory(
    user_id="user-123",
    memory_text="I prefer low-risk DeFi protocols like Aave",
    memory_type="preference",
    importance=0.9,
    session_id="session-456"
)
```

### Searching Memories
```python
from app.services.memo import memo_client

memories = await memo_client.search_memories(
    user_id="user-123",
    query_text="What DeFi protocols do I like?",
    top_k=5
)

for mem in memories:
    print(f"[{mem['memory_type']}] {mem['memory_text']} (similarity: {mem['similarity_score']:.2f})")
```

### Composing Prompts
```python
from app.services.prompt_composer import prompt_composer
from app.services.memo import memo_client

# Get memory context
memory_context = await memo_client.get_context_for_llm(
    user_id="user-123",
    current_query="Tell me about staking"
)

# Compose system prompt
system_prompt = prompt_composer.compose_system_prompt(
    memory_context=memory_context,
    user_emotion="excited",
    additional_context="User is new to DeFi"
)

# Use in LLM call
response = llm.generate(
    system_prompt=system_prompt,
    user_message="Tell me about staking"
)
```

## Testing

### Run Unit Tests
```bash
# Test MemO
pytest tests/test_memo.py -v

# Test PromptComposer
pytest tests/test_prompt_composer.py -v

# All tests
pytest tests/ -v
```

### Test with MEMO_ENABLED=false
```bash
export MEMO_ENABLED=false
pytest tests/test_memo.py::TestMemOClient::test_client_disabled -v
```

## Performance Targets

✅ **P95 Latency**: <60ms для поиска воспоминаний
✅ **Hit Rate**: >70% (воспоминания найдены для 70%+ запросов)
✅ **Availability**: Система работает без ошибок при MEMO_ENABLED=false

## Troubleshooting

### MemO не работает
1. Проверьте `MEMO_ENABLED=true` в `.env`
2. Проверьте, что sentence-transformers установлен: `pip list | grep sentence`
3. Проверьте логи: `tail -f logs/sophia.log | grep MemO`

### Промпты не перезагружаются
1. Проверьте, что файл `prompts/base_identity.md` существует
2. Проверьте права доступа к файлу: `ls -la prompts/`
3. Вызовите `/admin/reload-prompts` endpoint

### Низкая производительность
1. Проверьте метрики: `GET /admin/memo-metrics`
2. Уменьшите `MEMO_TOP_K` (например, с 5 до 3)
3. Увеличьте `MEMO_SIMILARITY_THRESHOLD` (например, с 0.7 до 0.8)
4. Проверьте индексы в Supabase: `CREATE INDEX ... USING ivfflat`

## Architecture Diagram

```
┌─────────────────┐
│   User Query    │
└────────┬────────┘
         │
         v
┌─────────────────────────────┐
│   MemO Client               │
│  - Generate embedding       │
│  - Search pgvector DB       │
│  - Return top-k memories    │
└────────┬────────────────────┘
         │
         v
┌─────────────────────────────┐
│   PromptComposer            │
│  - Load base_identity.md    │
│  - Add memory context       │
│  - Add emotion context      │
│  - Return composed prompt   │
└────────┬────────────────────┘
         │
         v
┌─────────────────────────────┐
│   LLM (Mistral/Claude)      │
│  - Generate response with   │
│    personalized context     │
└─────────────────────────────┘
```

## Next Steps

1. **Integ ration**: Integrate MemO + PromptComposer into LangGraph ResponseGenerator node
2. **Testing**: Run integration tests with real database
3. **Monitoring**: Set up metrics dashboard (Grafana + Prometheus)
4. **Optimization**: Fine-tune similarity threshold and embedding model

## Support

- Documentation: See `TASK_42597_IMPLEMENTATION.md` for full technical details
- Issues: Create issue in GitHub repo
- Contact: Team lead for questions
