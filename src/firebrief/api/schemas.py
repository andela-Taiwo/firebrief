"""Request and response shapes. The response never carries the raw question."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from firebrief.answer import AnswerResult
from firebrief.answer.types import Status


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


class QuoteResponse(BaseModel):
    marker: int | None
    text: str
    start: int | None
    end: int | None


class SourceResponse(BaseModel):
    n: int
    title: str
    heading: str
    edition: str
    url: str
    cited: bool = False
    quotes: tuple[QuoteResponse, ...] = ()


class RefusalResponse(BaseModel):
    reason: str
    message: str
    details: tuple[str, ...] = ()


class RedactionResponse(BaseModel):
    kind: str
    count: int


class AnswerResponse(BaseModel):
    request_id: str
    answer: str | None
    refusal: RefusalResponse | None
    sources: tuple[SourceResponse, ...]
    redactions: tuple[RedactionResponse, ...] = ()

    @classmethod
    def from_result(cls, result: AnswerResult) -> AnswerResponse:
        verified = _verified_quotes(result)
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
                    cited=source.chunk_id in {q.chunk_id for q in verified},
                    quotes=tuple(
                        QuoteResponse(
                            marker=quote.marker,
                            text=quote.quote,
                            start=quote.char_start,
                            end=quote.char_end,
                        )
                        for quote in verified
                        if quote.chunk_id == source.chunk_id
                    ),
                )
                for index, source in enumerate(result.sources, start=1)
            ),
            redactions=tuple(
                RedactionResponse(kind=finding.kind.value, count=finding.count)
                for finding in result.redactions
            ),
        )


def _verified_quotes(result: AnswerResult):  # type: ignore[no-untyped-def]
    if result.verification is None:
        return ()
    return tuple(
        check
        for claim in result.verification.claims
        for check in claim.checks
        if check.status is Status.VERIFIED and check.chunk_id is not None
    )
