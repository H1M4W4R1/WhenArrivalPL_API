"""Shared immutable base for API models."""

from pydantic import BaseModel, ConfigDict


class RequestModelBase(BaseModel):
    """Common response-model behaviour, isolated for future API changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
