"""Local face enrollment and authorization endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.capabilities.identity import IdentityError, IdentityResult

router = APIRouter(prefix="/identity", tags=["identity"])


class IdentityStatus(BaseModel):
    enrolled_profiles: list[str]
    session_authorized: bool


def _service(request: Request) -> FaceAuthorizationService:
    service: FaceAuthorizationService | None = request.app.state.identity_service
    if service is None:
        raise HTTPException(status_code=503, detail="Local face authorization is unavailable")
    return service


@router.get("/status", response_model=IdentityStatus)
async def identity_status(request: Request) -> IdentityStatus:
    service = _service(request)
    names, authorized = await asyncio.gather(
        asyncio.to_thread(service.profile_names),
        asyncio.to_thread(service.is_session_authorized),
    )
    return IdentityStatus(enrolled_profiles=names, session_authorized=authorized)


@router.post("/enroll", response_model=IdentityResult)
async def enroll_face(
    request: Request,
    name: Annotated[str, Form(min_length=1, max_length=100)],
    image: Annotated[UploadFile, File()],
) -> IdentityResult:
    try:
        return await asyncio.to_thread(_service(request).enroll, name, await image.read())
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/enroll-current", response_model=IdentityResult)
async def enroll_current(request: Request, name: str = "Rajesh") -> IdentityResult:
    try:
        return await asyncio.to_thread(_service(request).enroll_current, name)
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/verify", response_model=IdentityResult)
async def verify_face(request: Request, image: Annotated[UploadFile, File()]) -> IdentityResult:
    try:
        return await asyncio.to_thread(_service(request).verify, await image.read())
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/verify-current", response_model=IdentityResult)
async def verify_current(request: Request) -> IdentityResult:
    try:
        return await asyncio.to_thread(_service(request).verify_current)
    except IdentityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/profiles/{name}", status_code=204)
async def delete_profile(request: Request, name: str) -> None:
    if not await asyncio.to_thread(_service(request).delete_profile, name):
        raise HTTPException(status_code=404, detail="Face profile not found")
