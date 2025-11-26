"""Unit tests covering legacy chat endpoints and pipeline error handling."""

import os
import io
from types import SimpleNamespace
import importlib
import sys
from pathlib import Path

import types
from unittest.mock import patch

import pytest
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import config as app_config
from app.services.session_manager import SessionTurnManager
import app.deps as deps_module

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-service-key")

if "API_KEYS" in os.environ:
    existing = [k.strip() for k in os.environ["API_KEYS"].split(",") if k.strip()]
    if "test-key" not in existing:
        existing.append("test-key")
    os.environ["API_KEYS"] = ",".join(existing)
else:
    os.environ["API_KEYS"] = "test-key"

os.environ.setdefault(
    "SUPABASE_DEFAULT_USER_ID", "11111111-1111-1111-1111-111111111111"
)

sys.path.append(str(Path(__file__).resolve().parents[1]))

app_config.get_settings.cache_clear()
sys.modules.pop("main", None)

TEST_ISS = "https://example.supabase.co/auth/v1"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY_PEM = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


class _StubJWKClient:
    def get_signing_key_from_jwt(self, token: str):
        return SimpleNamespace(key=_PUBLIC_KEY_PEM, algorithm_name="RS256")


def _stub_get_jwk_client(issuer: str):
    return _StubJWKClient()


deps_module._get_jwk_client = _stub_get_jwk_client

Emotion = None


@pytest.fixture()
def client(monkeypatch):
    """Provide a fresh TestClient with API key checks disabled."""
    monkeypatch.setenv("API_KEYS", "test-key")
    app_config.get_settings.cache_clear()
    sys.modules.pop("main", None)
    app_module = importlib.import_module("main")
<<<<<<< HEAD
    chat_schemas = importlib.import_module("app.schemas.chat")
=======
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    monkeypatch.setattr(app_module, "verify_api_key", lambda authorization=None: None)

    async def _bypass(self, request, call_next):
        return await call_next(request)

    monkeypatch.setattr(app_module.APIKeyMiddleware, "dispatch", _bypass, raising=False)

    global Emotion
<<<<<<< HEAD
    Emotion = chat_schemas.Emotion
=======
    Emotion = app_module.Emotion
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
    return TestClient(app_module.app)


@pytest.fixture()
def protected_client():
    app_config.get_settings.cache_clear()
    sys.modules.pop("main", None)
    app_module = importlib.import_module("main")
    return TestClient(app_module.app)


def _encode_token(payload: dict | None = None) -> str:
    body = {"sub": "user-123", "iss": TEST_ISS}
    if payload:
        body.update(payload)
    return jwt.encode(
        body, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"}
    )


def auth(include_discord: bool = False, discord_id: str = "user-123"):
    headers = {"Authorization": f"Bearer {_encode_token()}"}
    if include_discord:
        headers["X-Discord-Id"] = discord_id
    return headers


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("message")


@patch(
    "app.services.mistral.transcribe_audio_with_voxtral", return_value="What is APY?"
)
@patch("app.services.emotion.analyze_emotion_text")
@patch("app.services.supabase.insert_emotion_score")
def test_transcribe_success(mock_ins, mock_emotion, mock_transcribe, client):
    mock_emotion.return_value = Emotion(label="neutral", confidence=0.81)
    wav_bytes = b"RIFF....WAVEfmt "  # fake wav
    files = {"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/transcribe", headers=auth(), files=files)
    assert r.status_code == 200
    data = r.json()
    assert "text" in data and data["text"] == "What is APY?"
    assert "emotion" in data and data["emotion"]["label"] in {
        "neutral",
        "positive",
        "negative",
        "unknown",
    }


def test_transcribe_wrong_type(client):
    files = {"file": ("notwav.mp3", io.BytesIO(b"xxx"), "audio/mpeg")}
    r = client.post("/transcribe", headers=auth(), files=files)
    assert r.status_code == 400


@patch(
    "app.services.mistral.generate_llm_reply",
    return_value="APY is annual percentage yield",
)
def test_generate_response(mock_gen, client):
    r = client.post("/generate-response", headers=auth(), json={"text": "Explain APY"})
    assert r.status_code == 200
    assert "reply" in r.json()


@patch("app.services.tts.synthesize_inworld", return_value=b"ID3mock-mp3")
@patch(
    "app.services.supabase.upload_audio_and_get_url",
    return_value="https://example.com/audio.mp3",
)
@patch("app.services.supabase.insert_emotion_score")
@patch("app.services.emotion.analyze_emotion_text")
def test_synthesize(mock_emotion, mock_ins, mock_up, mock_tts, client):
    mock_emotion.return_value = Emotion(label="positive", confidence=0.77)
    r = client.post("/synthesize", headers=auth(), json={"text": "Hello there"})
    assert r.status_code == 200
    data = r.json()
    assert data["audio_url"].startswith("http")
    assert data["emotion"]["label"] in {"neutral", "positive", "negative"}


@patch("app.deps.has_user_consent", return_value=True)
@patch(
    "app.services.mistral.transcribe_audio_with_voxtral", return_value="What is APY?"
)
@patch(
    "app.services.mistral.generate_llm_reply",
    return_value="APY stands for annual percentage yield",
)
@patch("app.services.tts.synthesize_inworld", return_value=b"ID3mock-mp3")
@patch(
    "app.services.supabase.upload_audio_and_get_url",
    return_value="https://example.com/resp.mp3",
)
@patch("app.services.supabase.insert_emotion_score")
@patch("app.services.supabase.insert_conversation_session")
@patch("app.services.emotion.analyze_emotion_text")
def test_chat(
    mock_emotion,
    mock_session,
    mock_ins,
    mock_up,
    mock_tts,
    mock_gen,
    mock_tr,
    mock_consent,
    client,
):
    mock_emotion.side_effect = [
        Emotion(label="neutral", confidence=0.83),
        Emotion(label="positive", confidence=0.78),
    ]
    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/chat", headers=auth(include_discord=True), files=files)
    assert r.status_code == 200
    data = r.json()
    assert set(
        ["transcript", "reply", "user_emotion", "sophia_emotion", "audio_url"]
    ).issubset(data.keys())


@patch("app.deps.has_user_consent", return_value=True)
def test_chat_turn_manager_propagates_cancel_checks(mock_consent, client, monkeypatch):
    """Ensure /chat pushes cancel callbacks through STT, LLM, and TTS while releasing the session turn."""
    assert Emotion is not None
<<<<<<< HEAD
    mistral_service = sys.modules["app.services.mistral"]
    emotion_service = sys.modules["app.services.emotion"]
    tts_service = sys.modules["app.services.tts"]
    supabase_service = sys.modules["app.services.supabase"]
    shared_services = sys.modules["app.services.shared_services"]
=======
    app_module = sys.modules["main"]
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)

    fake_manager = SessionTurnManager()
    raise_calls = []

    original_raise = fake_manager.raise_if_cancelled

    def _tracked_raise(self, turn_id):
        raise_calls.append(turn_id)
        return original_raise(turn_id)

    fake_manager.raise_if_cancelled = types.MethodType(_tracked_raise, fake_manager)
    monkeypatch.setattr(
<<<<<<< HEAD
        shared_services.shared_services,
=======
        app_module.shared_services,
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        "get_session_turn_manager",
        lambda: fake_manager,
        raising=False,
    )

    cancelled_stages = []

    def _fake_transcribe(_bytes, cancel_check=None):
        assert callable(cancel_check)
        cancel_check()
        cancelled_stages.append("stt")
        return "What is APY?"

    def _fake_generate(_text, cancel_check=None):
        assert callable(cancel_check)
        cancel_check()
        cancelled_stages.append("llm")
        return "APY stands for annual percentage yield."

    def _fake_tts(_text, cancel_check=None):
        assert callable(cancel_check)
        cancel_check()
        cancelled_stages.append("tts")
        return b"ID3mock-mp3"

    emotion_values = [
        Emotion(label="neutral", confidence=0.75),
        Emotion(label="positive", confidence=0.82),
    ]

    def _fake_emotion(_payload):
        return emotion_values.pop(0)

    monkeypatch.setattr(
<<<<<<< HEAD
        mistral_service,
=======
        app_module.mistral_service,
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        "transcribe_audio_with_voxtral",
        _fake_transcribe,
        raising=False,
    )
    monkeypatch.setattr(
<<<<<<< HEAD
        mistral_service, "generate_llm_reply", _fake_generate, raising=False
    )
    monkeypatch.setattr(tts_service, "synthesize_inworld", _fake_tts, raising=False)
    monkeypatch.setattr(
        emotion_service, "analyze_emotion_audio", _fake_emotion, raising=False
    )
    monkeypatch.setattr(
        supabase_service,
=======
        app_module.mistral_service, "generate_llm_reply", _fake_generate, raising=False
    )
    monkeypatch.setattr(app_module, "synthesize_inworld", _fake_tts, raising=False)
    monkeypatch.setattr(
        app_module, "analyze_emotion_audio", _fake_emotion, raising=False
    )
    monkeypatch.setattr(
        app_module.supabase_service,
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        "upload_audio_and_get_url",
        lambda *_args, **_kwargs: "https://example.com/audio.mp3",
        raising=False,
    )
    monkeypatch.setattr(
<<<<<<< HEAD
        supabase_service,
=======
        app_module.supabase_service,
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        "insert_conversation_session",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
<<<<<<< HEAD
        supabase_service,
=======
        app_module.supabase_service,
>>>>>>> 455d596 (Improve tier0 classifier: retries, metrics, cloud check)
        "insert_emotion_score",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    response = client.post("/chat", headers=auth(include_discord=True), files=files)

    assert response.status_code == 200
    assert set(cancelled_stages) == {"stt", "llm", "tts"}
    assert len(raise_calls) >= len(cancelled_stages)
    assert not fake_manager._active_by_session
    assert not fake_manager._turn_index


def test_chat_missing_consent_header_returns_403(client):
    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/chat", headers=auth(), files=files)
    assert r.status_code == 403


@patch("app.deps.has_user_consent", return_value=False)
def test_chat_consent_denied_returns_403(mock_consent, client):
    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/chat", headers=auth(include_discord=True), files=files)
    assert r.status_code == 403


def test_defi_chat_requires_consent_header(client):
    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/defi-chat", headers=auth(), files=files)
    assert r.status_code == 403


@patch("app.deps.has_user_consent", return_value=False)
def test_defi_chat_consent_denied(mock_consent, client):
    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/defi-chat", headers=auth(include_discord=True), files=files)
    assert r.status_code == 403


@patch("app.deps.has_user_consent", return_value=True)
@patch("app.services.langgraph_service.langgraph_service.process_conversation")
@patch("app.services.supabase.insert_conversation_session")
@patch("app.services.supabase.insert_emotion_score")
def test_defi_chat_consent_allows_flow(
    mock_ins_emotion, mock_ins_session, mock_process, mock_consent, client
):
    mock_process.return_value = {
        "session_id": "sess-123",
        "transcript": "What is staking?",
        "reply": "Staking locks tokens to secure the network.",
        "user_emotion": {"label": "neutral", "confidence": 0.7},
        "sophia_emotion": {"label": "positive", "confidence": 0.8},
        "audio_url": "https://example.com/audio.mp3",
        "intent": "defi_question",
        "context_memory": {},
        "fallbacks_used": {},
        "evaluation_logs": [],
        "evaluation_report": None,
    }
    wav_bytes = b"RIFF....WAVEfmt "
    files = {"file": ("u.wav", io.BytesIO(wav_bytes), "audio/wav")}
    r = client.post("/defi-chat", headers=auth(include_discord=True), files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "sess-123"
    assert data["user_emotion"]["label"] == "neutral"


def test_text_chat_requires_consent_header(client):
    r = client.post("/text-chat", headers=auth(), json={"message": "Hello"})
    assert r.status_code == 403


@patch("app.deps.has_user_consent", return_value=True)
@patch("app.services.langgraph_service.langgraph_service.process_text_conversation")
@patch("app.services.supabase.insert_conversation_session")
@patch("app.services.supabase.insert_emotion_score")
def test_text_chat_consent_allows_flow(
    mock_ins_emotion, mock_ins_session, mock_process, mock_consent, client
):
    mock_process.return_value = {
        "session_id": "sess-text",
        "transcript": "Tell me about DeFi",
        "reply": "DeFi enables permissionless finance.",
        "user_emotion": {"label": "neutral", "confidence": 0.75},
        "sophia_emotion": {"label": "neutral", "confidence": 0.6},
        "audio_url": "https://example.com/audio.mp3",
        "intent": "defi_question",
        "context_memory": {},
        "fallbacks_used": {},
        "evaluation_logs": [],
        "evaluation_report": None,
    }
    r = client.post(
        "/text-chat", headers=auth(include_discord=True), json={"message": "Hello"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "sess-text"


def test_missing_auth(protected_client):
    protected_client.get("/")  # public endpoint OK
    files = {"file": ("u.wav", io.BytesIO(b"RIFF"), "audio/wav")}
    r2 = protected_client.post("/transcribe", files=files)
    assert r2.status_code == 401
