from typing import Any

from pydantic import BaseModel, Field


class PublicConfig(BaseModel):
    oracleConfigured: bool
    oracleMode: str
    dataFilePresent: bool
    activeOperation: bool
    limits: dict[str, int]


class ConnectionTestResponse(BaseModel):
    success: bool = True
    capabilities: dict[str, Any]


class ScanRequest(BaseModel):
    schemas: list[str] = Field(min_length=1)
    objectTypes: list[str] = Field(default_factory=list)
    includeSourceCode: bool = False
    resolveExternalReferences: bool = True
    includeSchedulerObjects: bool = False
