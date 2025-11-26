# Быстрый старт - Audio Queue + Barge-In (Задача #42333)

## ✅ Что реализовано

### AudioQueueManager (`app/services/audio_queue.py`)
- ✅ Очередь аудио-сегментов с sequential playback
- ✅ Barge-in < 200ms при VAD триггере
- ✅ Thread-safe для concurrent sessions
- ✅ Session isolation
- ✅ Comprehensive stats tracking

### WebSocket Integration (`main.py`)
- ✅ VAD автоматически вызывает `audio_queue.cancel_all()`
- ✅ TTS audio enqueue вместо direct send
- ✅ Background playback loop
- ✅ Session cleanup on disconnect

### Tests
- ✅ `tests/test_audio_queue.py` - comprehensive pytest suite
- ✅ `test_audio_queue_simple.py` - все 5 тестов прошли
- ✅ Проверена работа с 10 concurrent sessions

---

## 🚀 Запуск с Docker (OrbStack/Docker Desktop)

### 1. Настройка переменных окружения

```bash
# Скопируйте шаблон
cp .env.example .env

# Отредактируйте .env и заполните свои API keys:
# - MISTRAL_API_KEY
# - INWORLD_API_KEY
# - GOOGLE_API_KEY
# - OPENAI_API_KEY
# - ANTHROPIC_API_KEY
# - SUPABASE_URL
# - SUPABASE_SERVICE_KEY
# - SUPABASE_KEY
# - SUPABASE_DB_DSN
# - API_KEYS
```

### 2. Запуск контейнеров

```bash
# Собрать контейнеры (если еще не собрали)
docker compose build

# Запустить backend + Redis
docker compose up

# Или в фоне
docker compose up -d

# Посмотреть логи
docker compose logs -f sophia-backend
```

### 3. Проверка работы

Backend доступен на `http://localhost:8000`

**Health check:**
```bash
curl http://localhost:8000/health
```

**WebSocket endpoint с Audio Queue:**
```
ws://localhost:8000/ws/voice
```

### 4. Остановка

```bash
# Остановить контейнеры
docker compose down

# Удалить volumes (очистить Redis data)
docker compose down -v
```

---

## 🧪 Тестирование локально (без Docker)

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Запуск простого теста

```bash
# Запустить standalone тест Audio Queue
python test_audio_queue_simple.py
```

**Ожидаемый результат:**
```
============================================================
AudioQueueManager Test Suite
Testing Task #42333 Requirements
============================================================
Test 1: Basic Enqueue...
✓ Basic enqueue passed

Test 2: Barge-in Timing (<200ms requirement)...
✓ Barge-in timing passed: 0.02ms (< 200ms)

Test 3: 10 Concurrent Sessions...
✓ 10 concurrent sessions passed: 10/10 successful

Test 4: Sequential Playback (no overlaps)...
✓ Sequential playback passed: correct order, no overlaps

Test 5: Stats Tracking...
✓ Stats tracking passed: played=3, cancelled=0

============================================================
✓ ALL TESTS PASSED
============================================================
```

### 3. Запуск pytest suite

```bash
# Полный тест suite (требует pytest)
pytest tests/test_audio_queue.py -v
```

### 4. Запуск backend напрямую

```bash
# Убедитесь что .env настроен и Redis запущен
python main.py

# Или с uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📊 Архитектура Audio Queue

### Flow диаграмма

```
User Voice Input (WebSocket)
         ↓
    VAD Detection
         ↓
   [Speech Start?]
         ↓ YES
   ┌─────────────────────────┐
   │ audio_queue.cancel_all()│  <-- Barge-in < 200ms
   │ - Cancel current TTS    │
   │ - Clear pending queue   │
   └─────────────────────────┘
         ↓
   Process Speech → LLM Response
         ↓
   Split into sentences
         ↓
   FOR EACH sentence:
      TTS synthesis
         ↓
   audio_queue.enqueue()  <-- Add to queue
         ↓
   Background playback loop
         ↓
   Sequential delivery (no overlaps)
```

### Session Isolation

```python
# Each WebSocket connection = unique session
session_id = str(uuid.uuid4())

# Isolated queues per session
audio_queue_manager._queues[session_id]
audio_queue_manager._states[session_id]
audio_queue_manager._current_segments[session_id]

# 10+ concurrent sessions supported ✅
```

---

## 🎯 Критерии приёмки - Выполнены

| Критерий | Статус | Детали |
|----------|--------|---------|
| Sequential playback без перекрытий | ✅ | Queue manager обеспечивает |
| Прерывание TTS < 200ms | ✅ | 0.02ms по тестам |
| VAD триггер → queue.cancel() | ✅ | Интегрировано в main.py:795-811 |
| 10+ одновременных сессий | ✅ | Тест прошел 10/10 |
| Звук очищается при прерывании | ✅ | cancel_all() очищает queue |

---

## 🐛 Troubleshooting

### Redis connection failed
```bash
# Проверьте что Redis запущен
docker compose ps

# Перезапустите контейнеры
docker compose restart redis
```

### API key errors
```bash
# Проверьте .env файл
cat .env | grep API_KEY

# Убедитесь что нет пробелов вокруг =
# ПРАВИЛЬНО: MISTRAL_API_KEY=sk_xxx
# НЕПРАВИЛЬНО: MISTRAL_API_KEY = sk_xxx
```

### Port 8000 already in use
```bash
# Найти процесс
lsof -ti:8000

# Убить процесс
kill -9 $(lsof -ti:8000)

# Или измените порт в docker-compose.yml
```

---

## 📝 Логи и мониторинг

### Важные логи Audio Queue

```bash
# Barge-in events
grep "BARGE-IN triggered" docker-compose.log

# Queue stats
grep "final stats" docker-compose.log

# Interruption timing
grep "interruption_time" docker-compose.log
```

### Пример лога успешного barge-in

```
WS: speech started at 0 bytes (amp=450.2)
WS Session abc-123: BARGE-IN triggered (cancelled=True, cleared=3, interruption_time=0.18ms)
WS Session abc-123: final stats - played=5, cancelled=1, total_cancellations=1, last_interruption_ms=0.18
```

---

## 🔗 Связанные файлы

- **AudioQueueManager**: `app/services/audio_queue.py`
- **WebSocket integration**: `main.py` (lines 752-970)
- **Tests**: `tests/test_audio_queue.py`, `test_audio_queue_simple.py`
- **Docker**: `docker-compose.yml`, `Dockerfile`
- **Config**: `.env.example`

---

## ✨ Next Steps

После тестирования можно:
1. Создать Pull Request в `main` branch
2. Deploy на staging/production
3. Мониторинг метрик barge-in timing
4. Собрать feedback от пользователей
