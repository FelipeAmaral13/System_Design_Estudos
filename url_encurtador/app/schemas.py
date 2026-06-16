import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class UrlCreateRequest(BaseModel):
    original_url: HttpUrl
    ttl_days: int | None = Field(default=None, ge=1, le=3650)


class UrlCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_url: str
    original_url: str
    created_at: dt.datetime
    expires_at: dt.datetime | None


class UrlRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    original_url: str
    created_at: dt.datetime
    expires_at: dt.datetime | None
