import asyncio
import logging
import time
from typing import Callable

from starlette.websockets import WebSocketDisconnect

from app.audio_utils import avg_abs_pcm16, wav_header_pcm16


SAMPLE_RATE = 16000
BYTES_PER_SEC = SAMPLE_RATE * 2  # pcm16 mono
SILENCE_THRESHOLD = 300
SILENCE_MS = 600
SILENCE_BYTES = int(BYTES_PER_SEC * (SILENCE_MS / 1000.0))

logger = logging.getLogger(__name__)

async def receive_audio_chunks(
    websocket,
    session_id,
    in_speech: asyncio.Event,
    manager,
    audio_queue,
    barge_in_callback: Callable
):
    pcm_buffer = bytearray()
    last_voice_activity = 0
    utter_start_pos = 0
    while True:
        msg = await websocket.receive()
        if "bytes" in msg and msg["bytes"] is not None:
            chunk = msg["bytes"]
            pcm_buffer.extend(chunk)
            now = time.time()
            recent = (
                pcm_buffer[-SILENCE_BYTES:]
                if len(pcm_buffer) > SILENCE_BYTES
                else pcm_buffer
            )
            amp = avg_abs_pcm16(recent)
            if amp > SILENCE_THRESHOLD:
                if not in_speech.is_set():
                    in_speech.set()
                    utter_start_pos = max(0, len(pcm_buffer) - len(recent))
                    barge_in_start = time.time()
                    active_turn = manager.get_active_turn(session_id)
                    interrupted_turn_id = (
                        active_turn.turn_id if active_turn else None
                    )
                    if interrupted_turn_id:
                        manager.request_cancel(turn_id=interrupted_turn_id)
                    current_cancelled, queue_cleared = audio_queue.cancel_all(
                        session_id
                    )
                    barge_in_ms = (time.time() - barge_in_start) * 1000

                    await barge_in_callback(
                        barge_in_ms,
                        current_cancelled,
                        queue_cleared,
                        interrupted_turn_id
                    )
                    if barge_in_ms > 200:
                        logger.warning(
                            f"WS Session {session_id}: barge-in interruption took {barge_in_ms:.2f}ms (>200ms budget)"
                        )
                last_voice_activity = now
                continue

            if in_speech.is_set() and (now - last_voice_activity) * 1000 >= SILENCE_MS:
                utter_bytes = bytes(pcm_buffer[utter_start_pos:])
                yield wav_header_pcm16(len(utter_bytes) // 2) + utter_bytes
                pcm_buffer.clear()
                last_voice_activity = 0
        elif 'type' in msg and msg['type'] == 'websocket.disconnect':
            break