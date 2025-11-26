# Transcript Debugging Notes

## Summary
- Added temporary DEBUG/WARNING logs around `state["transcript"]` reads and writes in `AudioIngestor`, `IntentAnalyzer`, and `ResponseGenerator` to trace transcript propagation.
- Running the full `SophiaLangGraph.process_conversation` pipeline against `full_test_output.wav` with DEBUG logging shows `transcribe_audio_with_voxtral` returning an empty string and the Gemini fallback exhausting retries, leaving `state["transcript"]` blank.
- Downstream nodes log the empty transcript, confirming the blank value originates in `AudioIngestor` after STT failure.

## Reproduction
```bash
python - <<'PY'
import logging
logging.basicConfig(level=logging.DEBUG)
from app.langgraph_nodes import SophiaLangGraph

with open('full_test_output.wav', 'rb') as f:
    audio_bytes = f.read()

graph = SophiaLangGraph()
state = graph.process_conversation(audio_bytes)
print('Final transcript repr:', repr(state['transcript']))
print('Fallback used:', state.get('fallback_used'))
PY
```

Key log excerpts:
- Voxtral STT immediately returns an empty string, triggering a warning after the Gemini fallback also fails: `AudioIngestor: transcribe_audio_with_voxtral returned '' (len=0)` followed by repeated `403 PERMISSION_DENIED` responses and `AudioIngestor produced empty transcript...`.
- Intent and response nodes both record receiving an empty transcript, which flows through to a generic "I didn't catch that" response.

See chunk `97fe20` for the full output.

## Minimal corrective change
Update `AudioIngestor` so that if both Voxtral and fallback paths fail to produce a non-empty transcript, it short-circuits the pipeline by:
1. Setting a dedicated `state["transcript_error"] = "stt_failed"` flag (or similar) and leaving the transcript untouched.
2. Returning early so downstream nodes can handle the error case (e.g., respond with a clear "transcription failed" message instead of empty intent/small talk heuristics).

This prevents later nodes from working with blank transcripts and makes the failure explicit for the caller.
