"""Pydantic schemas for chat endpoints."""

from typing import Optional

from pydantic import BaseModel


class Emotion(BaseModel):
    label: str
    confidence: float


class TranscriptionResponse(BaseModel):
    text: str
    emotion: Emotion


class GenerateResponse(BaseModel):
    reply: str
    tone: Optional[str] = "neutral"


class SynthesizeResponse(BaseModel):
    audio_url: str
    emotion: Emotion


class ChatResponse(BaseModel):
    transcript: str
    reply: str
    user_emotion: Emotion
    sophia_emotion: Emotion
    audio_url: str
    intent: Optional[str] = None
    context_memory: Optional[dict] = None
    evaluation_report: Optional[dict] = None


class DefiChatResponse(BaseModel):
    session_id: str
    transcript: str
    reply: str
    response_path: Optional[str] = None
    user_emotion: Emotion
    sophia_emotion: Emotion
    audio_url: str
    intent: str
    context_memory: dict
    fallbacks_used: dict
    evaluation_logs: list
    evaluation_report: Optional[dict] = None


class TextChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class GenerateRequest(BaseModel):
    text: str


class SynthesizeRequest(BaseModel):
    text: str
