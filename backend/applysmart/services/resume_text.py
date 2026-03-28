from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader


def extract_text_from_pdf(data: bytes) -> tuple[str | None, dict[str, Any]]:
    meta: dict[str, Any] = {"bytes": len(data)}
    try:
        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        for page in reader.pages[:30]:
            t = page.extract_text()
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        meta["pages"] = len(reader.pages)
        if not text:
            return None, {**meta, "error": "no_text_extracted"}
        return text[:120_000], meta
    except Exception as e:
        return None, {**meta, "error": str(e)[:200]}


def extract_text_from_upload(filename: str, data: bytes) -> tuple[str | None, dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(data)
    if name.endswith((".txt", ".md")):
        try:
            return data.decode("utf-8", errors="replace")[:120_000], {"encoding": "utf-8"}
        except Exception as e:
            return None, {"error": str(e)[:200]}
    return None, {"error": "unsupported_file_type"}
