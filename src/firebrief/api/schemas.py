"""Request and response shapes. The response never carries the raw question."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from firebrief.answer import AnswerResult


class MagicLinkRequest(BaseModel):
    tenant_id: uuid.UUID
    email: str = Field(min_length=3, max_length=320)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class SessionResponse(BaseModel):
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str


class AnswerRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class SourceResponse(BaseModel):
    n: int
    title: str
    heading: str
    edition: str
    url: str


class RefusalResponse(BaseModel):
    reason: str
    message: str
    details: tuple[str, ...] = ()


class AnswerResponse(BaseModel):
    request_id: str
    answer: str | None
    refusal: RefusalResponse | None
    sources: tuple[SourceResponse, ...]
    redactions: tuple[str, ...] = ()

    @classmethod
    def from_result(cls, result: AnswerResult) -> AnswerResponse:
        return cls(
            request_id=result.request_id,
            answer=result.answer,
            refusal=(
                RefusalResponse(
                    reason=result.refusal.reason.value,
                    message=result.refusal.message,
                    details=result.refusal.details,
                )
                if result.refusal is not None
                else None
            ),
            sources=tuple(
                SourceResponse(
                    n=index,
                    title=source.document_title,
                    heading=source.heading_path,
                    edition=source.edition,
                    url=source.source_url,
                )
                for index, source in enumerate(result.sources, start=1)
            ),
            redactions=tuple(
                f"{finding.kind.value}:{finding.count}" for finding in result.redactions
            ),
        )
