# Руководство по Миграции: MemO Memory System (Task #42597)

## Обзор
Эта миграция добавляет систему MemO (Intelligent Memory) с семантическим хранилищем памяти на основе pgvector.

## Предварительные Требования
- PostgreSQL с установленным расширением pgvector
- Проект Supabase с доступом к базе данных
- Admin/service role ключ для Supabase

## Шаги Миграции для Production Supabase

### Шаг 1: Включить расширение pgvector
```sql
-- Подключитесь к вашей базе Supabase через SQL Editor
CREATE EXTENSION IF NOT EXISTS vector;
```

### Шаг 2: Применить миграцию базы данных

**Вариант A: Используя Alembic (Рекомендуется)**
```bash
# Установить переменные окружения
export SUPABASE_DB_DSN="postgresql://postgres:[ВАШ-ПАРОЛЬ]@db.[ВАШ-PROJECT-REF].supabase.co:5432/postgres"

# Запустить миграцию
alembic upgrade head
```

**Вариант B: Ручное выполнение SQL**

Выполните этот SQL в Supabase SQL Editor:

```sql
-- Создать таблицу user_memories с поддержкой pgvector
CREATE TABLE IF NOT EXISTS user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    memory_text TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('preference', 'fact', 'emotion', 'context')),
    importance FLOAT DEFAULT 0.8 CHECK (importance >= 0 AND importance <= 1),
    embedding vector(384),  -- sentence-transformers/all-MiniLM-L6-v2 размерность
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Создать индексы для производительности
CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_type ON user_memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_user_memories_created_at ON user_memories(created_at DESC);

-- Создать IVFFlat индекс для векторного поиска по сходству
-- Для < 1M строк: lists = rows / 1000
-- Для > 1M строк: lists = sqrt(rows)
CREATE INDEX IF NOT EXISTS idx_user_memories_embedding
ON user_memories
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Создать триггер updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_user_memories_updated_at
    BEFORE UPDATE ON user_memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Выдать права доступа
GRANT SELECT, INSERT, UPDATE, DELETE ON user_memories TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON user_memories TO service_role;
```

### Шаг 3: Проверить миграцию

```sql
-- Проверить что таблица существует
SELECT EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_name = 'user_memories'
);

-- Проверить расширение pgvector
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Проверить индексы
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'user_memories';
```

## Конфигурация Окружения

Добавьте эти переменные в production `.env`:

```bash
# Конфигурация MemO
MEMO_ENABLED=true
MEMO_TOP_K=5
MEMO_SIMILARITY_THRESHOLD=0.7
MEMO_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Supabase (должны уже существовать)
SUPABASE_URL=https://[your-project-ref].supabase.co
SUPABASE_KEY=[your-anon-key]
SUPABASE_SERVICE_KEY=[your-service-role-key]
SUPABASE_DB_DSN=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
```

## Тестирование Миграции

### 1. Тестовый API запрос
```bash
curl -X POST https://your-domain.com/text-chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "message": "Я предпочитаю детальные технические объяснения",
    "user_id": "test-user-001",
    "session_id": "test-session-001"
  }'
```

### 2. Проверка базы данных
```sql
-- Посмотреть сохраненные воспоминания
SELECT
    user_id,
    memory_type,
    LEFT(memory_text, 50) as preview,
    importance,
    created_at
FROM user_memories
ORDER BY created_at DESC
LIMIT 10;

-- Подсчитать воспоминания по пользователям
SELECT
    user_id,
    COUNT(*) as memory_count,
    COUNT(DISTINCT memory_type) as type_count
FROM user_memories
GROUP BY user_id;
```

### 3. Мониторинг производительности
```sql
-- Проверить P95 latency для векторного поиска (должно быть < 60ms)
EXPLAIN ANALYZE
SELECT
    memory_text,
    1 - (embedding <=> '[0.1, 0.2, ...]'::vector) as similarity
FROM user_memories
WHERE user_id = 'test-user-001'
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;
```

## План Отката

Если нужно откатить изменения:

```bash
# Используя Alembic
alembic downgrade -1

# Или вручную через SQL
DROP TABLE IF EXISTS user_memories CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
```

## Оптимизация Производительности

После миграции, если у вас > 10k воспоминаний:

```sql
-- Пересоздать IVFFlat индекс с оптимизированным параметром lists
DROP INDEX IF EXISTS idx_user_memories_embedding;

CREATE INDEX idx_user_memories_embedding
ON user_memories
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1000);  -- Настроить в зависимости от количества строк

-- Проанализировать таблицу для планировщика запросов
ANALYZE user_memories;
```

## Решение Проблем

### Ошибка: "extension vector does not exist"
```sql
-- Установить pgvector (требует superuser)
CREATE EXTENSION vector;
```

### Ошибка: "permission denied for relation user_memories"
```sql
-- Выдать права доступа
GRANT ALL ON user_memories TO authenticated;
GRANT ALL ON user_memories TO service_role;
```

### Медленный векторный поиск
```sql
-- Проверить используется ли индекс
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM user_memories
ORDER BY embedding <=> '[...]'::vector
LIMIT 5;

-- Если индекс не используется, увеличить maintenance_work_mem и перестроить
SET maintenance_work_mem = '512MB';
REINDEX INDEX idx_user_memories_embedding;
```

## Чеклист После Миграции

- [ ] Расширение pgvector включено
- [ ] Таблица user_memories создана
- [ ] Все индексы созданы (включая IVFFlat)
- [ ] Триггеры и функции созданы
- [ ] Права доступа выданы
- [ ] Переменные окружения настроены
- [ ] Backend перезапущен с новой конфигурацией
- [ ] API тест успешен (память сохранена)
- [ ] Запрос к БД успешен (память извлечена)
- [ ] Логи показывают метрики MemO (latency < 60ms P95)
- [ ] Hot reload работает (изменения prompts/base_identity.md применяются)

## Поддержка

Для вопросов или проблем:
- Проверить логи: `docker-compose logs -f sophia-backend | grep -i memo`
- Просмотреть метрики: `./check_memo_metrics.sh`
- Мониторинг в реальном времени: `./watch_memo_logs.sh`
