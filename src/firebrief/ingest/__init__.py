"""Corpus ingestion: fetch, parse, licence-check and version guidance documents."""

from firebrief.ingest.licence import ALLOWED_LICENCES, LicenceNotAccepted, check_licence
from firebrief.ingest.parse import EmptyDocument, parse_sections
from firebrief.ingest.sources import FakeSource, GovUkContentApi
from firebrief.ingest.store import IngestResult, content_hash, ingest
from firebrief.ingest.types import DocumentSource, ParsedSection, SourceDocument

__all__ = [
    "ALLOWED_LICENCES",
    "DocumentSource",
    "EmptyDocument",
    "FakeSource",
    "GovUkContentApi",
    "IngestResult",
    "LicenceNotAccepted",
    "ParsedSection",
    "SourceDocument",
    "check_licence",
    "content_hash",
    "ingest",
    "parse_sections",
]
