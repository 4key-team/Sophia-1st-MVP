# Task #42805: Fix session_id handling in text chat

## Problem
The text chat streaming endpoint (`/text-chat/stream`) was not returning `session_id` in SSE events, making it impossible for the frontend to track and reuse sessions across multiple messages.

## Solution

### Backend Changes (main.py)

1. **Added `meta` event** at the start of streaming response:
   - Sends `session_id` immediately when streaming starts
   - Format: `event: meta\ndata: {"session_id": "uuid-here"}\n\n`

2. **Added `session_id` to `reply_done` event**:
   - Includes `session_id` along with reply and user_emotion
   - Format: `event: reply_done\ndata: {"reply": "...", "user_emotion": {...}, "session_id": "uuid-here"}\n\n`

3. **Added `session_id` to `audio_url` event**:
   - Includes `session_id` along with audio_url and emotions
   - Format: `event: audio_url\ndata: {"audio_url": "...", "sophia_emotion": {...}, "user_emotion": {...}, "session_id": "uuid-here"}\n\n`

4. **Updated API documentation**:
   - Docstring for `/text-chat/stream` now documents all events including `session_id`

### Frontend Changes (ChatInterface.tsx)

1. **Added `meta` event handler**:
   - Extracts and updates `session_id` from the initial meta event

2. **Added `session_id` extraction in `reply_done` handler**:
   - Updates `sessionId` state if present in the event

3. **Added `session_id` extraction in `audio_url` handler**:
   - Updates `sessionId` state if present in the event

### Event Flow

```
1. Frontend sends: POST /text-chat/stream with { message, session_id }
2. Backend emits:
   - event: meta, data: { session_id }          ← NEW
   - event: token, data: chunk1
   - event: token, data: chunk2
   - ...
   - event: reply_done, data: { reply, user_emotion, session_id }    ← UPDATED
   - event: audio_url, data: { audio_url, sophia_emotion, user_emotion, session_id }  ← UPDATED
3. Frontend extracts session_id and uses it for next message
```

## Testing

A comprehensive test suite has been created in `test_text_chat_session_id.py`:

1. **Test 1**: Non-streaming endpoint returns `session_id`
2. **Test 2**: Streaming endpoint returns `session_id` in all relevant events
3. **Test 3**: Session persistence across multiple messages

### Running the tests:

```bash
# Ensure backend is running
uv run python main.py

# In another terminal, run tests
uv run python test_text_chat_session_id.py
```

## Verification

### Non-streaming endpoint
```bash
curl -X POST http://localhost:8000/text-chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is DeFi?"}'
```

Expected response includes:
```json
{
  "session_id": "uuid-here",
  "transcript": "What is DeFi?",
  "reply": "...",
  ...
}
```

### Streaming endpoint
```bash
curl -X POST http://localhost:8000/text-chat/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is DeFi?"}'
```

Expected SSE events:
```
event: meta
data: {"session_id": "uuid-here"}

event: token
data: DeFi

event: token
data:  stands

event: reply_done
data: {"reply": "DeFi stands for...", "user_emotion": {...}, "session_id": "uuid-here"}

event: audio_url
data: {"audio_url": "...", "sophia_emotion": {...}, "user_emotion": {...}, "session_id": "uuid-here"}
```

## Impact

### Backend
- ✅ No breaking changes
- ✅ Added new `meta` event (backwards compatible)
- ✅ Added `session_id` to existing events (backwards compatible - frontends can ignore)
- ✅ Better session tracking and debugging

### Frontend
- ✅ Can now properly track session across messages
- ✅ Session persistence working correctly
- ✅ Better conversation context management

## Files Modified

1. `main.py`:
   - Line ~1973: Added `meta` event emission
   - Line ~2048: Added `session_id` to `reply_done` payload
   - Line ~2091: Added `session_id` to `audio_url` payload
   - Line ~1949: Updated API docstring

2. `frontend-nextjs/app/components/ChatInterface.tsx`:
   - Line ~129: Added `meta` event handler
   - Line ~145: Added `session_id` extraction in `reply_done`
   - Line ~160: Added `session_id` extraction in `audio_url`

3. `test_text_chat_session_id.py`: New comprehensive test suite

## Related Tasks

- Task #42785: Define prompt data structures (completed)
- Task #42787: WebSocket LangGraph pipeline (completed)
