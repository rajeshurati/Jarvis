"""Local conversational assistant endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from jarvis.application.assistant_service import AssistantService
from jarvis.application.speech_service import SpeechSynthesisService
from jarvis.capabilities.automation import AutomationError
from jarvis.capabilities.language import LanguageModelError
from jarvis.capabilities.speech import SpeechError

router = APIRouter(prefix="/assistant", tags=["assistant"])


class CommandRequest(BaseModel):
    """Validated natural-language command."""

    text: str = Field(min_length=1, max_length=4_000)


class CommandResponse(BaseModel):
    """Spoken reply and optional action name."""

    reply: str
    action: str | None
    target_url: str | None = None
    desktop_action: str | None = None


class SpeechRequest(BaseModel):
    """Validated text-to-speech request."""

    text: str = Field(min_length=1, max_length=2_000)


def _assistant(request: Request) -> AssistantService:
    service: AssistantService | None = request.app.state.assistant_service
    if service is None:
        raise HTTPException(status_code=503, detail="Local assistant is unavailable")
    return service


def _speech(request: Request) -> SpeechSynthesisService:
    service: SpeechSynthesisService | None = request.app.state.speech_service
    if service is None:
        raise HTTPException(status_code=503, detail="Local speech is unavailable")
    return service


@router.post("/respond", response_model=CommandResponse)
async def respond(payload: CommandRequest, request: Request) -> CommandResponse:
    """Execute a safe command or answer with the local model."""
    try:
        reply = await _assistant(request).respond(payload.text)
        return CommandResponse(
            reply=reply.text,
            action=reply.action,
            target_url=reply.target_url,
            desktop_action=reply.desktop_action,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AutomationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except LanguageModelError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/speak")
async def speak(payload: SpeechRequest, request: Request) -> Response:
    """Render a spoken response using the local Windows voice."""
    try:
        return Response(await _speech(request).synthesize(payload.text), media_type="audio/wav")
    except (ValueError, SpeechError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
