from typing import Any

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("schemas", "objectTypes")
    @classmethod
    def clean_unique_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) != len(set(cleaned)):
            cleaned = list(dict.fromkeys(cleaned))
        return cleaned
