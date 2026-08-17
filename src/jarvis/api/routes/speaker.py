"""Local speaker enrollment and recognition endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated, cast

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from jarvis.application.speaker_service import SpeakerRecognitionService
from jarvis.capabilities.identity import IdentityError, SpeakerResult

router = APIRouter(prefix="/speaker", tags=["speaker"])


class SpeakerStatus(BaseModel):
    available: bool
    enrolled_profiles: list[str]
    security_note: str = "Voice recognition is a convenience signal, not sole authorization."


def _service(request: Request) -> SpeakerRecognitionService:
    service = cast(SpeakerRecognitionService | None, request.app.state.speaker_service)
    if service is None:
        raise HTTPException(status_code=503, detail="Local speaker model is unavailable")
    return service


@router.get("/status", response_model=SpeakerStatus)
async def status(request: Request) -> SpeakerStatus:
    service = cast(SpeakerRecognitionService | None, request.app.state.speaker_service)
    if service is None:
        return SpeakerStatus(available=False, enrolled_profiles=[])
    names = await asyncio.to_thread(service.profile_names)
    return SpeakerStatus(available=True, enrolled_profiles=names)


@router.post("/enroll-current", response_model=SpeakerResult)
async def enroll_current(request: Request, name: str = "Rajesh") -> SpeakerResult:
    try:
        return await asyncio.to_thread(_service(request).enroll_current, name)
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/verify-current", response_model=SpeakerResult)
async def verify_current(request: Request) -> SpeakerResult:
    try:
        return await asyncio.to_thread(_service(request).verify_current)
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/enroll-audio", response_model=SpeakerResult)
async def enroll_audio(
    request: Request,
    audio: Annotated[UploadFile, File()],
    name: str = "Rajesh",
) -> SpeakerResult:
    """Enroll a transient sample captured by the signed-in desktop process."""
    try:
        content = await audio.read(25 * 1024 * 1024 + 1)
        return await asyncio.to_thread(_service(request).enroll_audio, name, content)
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/verify-audio", response_model=SpeakerResult)
async def verify_audio(
    request: Request, audio: Annotated[UploadFile, File()]
) -> SpeakerResult:
    """Verify a transient sample captured by the signed-in desktop process."""
    try:
        content = await audio.read(25 * 1024 * 1024 + 1)
        return await asyncio.to_thread(_service(request).verify_audio, content)
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/profiles/{name}", status_code=204)
async def delete_profile(request: Request, name: str) -> None:
    if not await asyncio.to_thread(_service(request).delete_profile, name):
        raise HTTPException(status_code=404, detail="Speaker profile not found")
