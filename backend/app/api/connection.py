import asyncio

from fastapi import APIRouter, Request

from app.api.models import ConnectionTestResponse
from app.config import Settings
from app.oracle.capabilities import discover_capabilities
from app.oracle.connection import credentials_from_settings


router = APIRouter(prefix="/connection", tags=["connection"])


async def _capabilities(settings: Settings) -> dict:
    credentials = credentials_from_settings(settings)
    return await asyncio.to_thread(discover_capabilities, credentials)


@router.post("/test", response_model=ConnectionTestResponse)
async def test_connection(request: Request) -> ConnectionTestResponse:
    capabilities = await _capabilities(request.app.state.settings)
    return ConnectionTestResponse(capabilities=capabilities)


@router.get("/capabilities")
async def get_capabilities(request: Request) -> dict:
    return await _capabilities(request.app.state.settings)
