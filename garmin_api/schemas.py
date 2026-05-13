"""Pydantic request and response models for the Garmin HTTP API."""

from typing import Any

from pydantic import BaseModel, Field


class AccountCreateRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    label: str | None = None
    is_cn: bool = False


class AccountCreateResponse(BaseModel):
    account_id: str
    api_key: str
    mfa_required: bool = False
    message: str


class MfaRequest(BaseModel):
    mfa_code: str = Field(min_length=3)


class AccountStatusResponse(BaseModel):
    account_id: str
    label: str | None
    authenticated: bool


class DataResponse(BaseModel):
    account_id: str
    data: Any
    cached: bool = False
