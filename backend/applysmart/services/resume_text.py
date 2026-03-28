from __future__ import annotations

from io import BytesIO
from typing import Any

import pdfplumber
import fitz # PyMuPDF


def extract_text_from_pdf(data: bytes) -> tuple[str | None, dict[str, Any]]:
    meta: dict[str, Any] = {"bytes": len(data)}
    text = ""
    
    # Strategy 1: pdfplumber (best for structured resumes)
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            parts = []
            for page in pdf.pages[:30]:
                t = page.extract_text(layout=True)
                if t:
                    parts.append(t)
            text = "\n".join(parts).strip()
            meta["pages"] = len(pdf.pages)
            meta["method"] = "pdfplumber"
    except Exception as e:
        meta["pdfplumber_error"] = str(e)

    # Strategy 2: PyMuPDF (fallback for complex layouts)
    if not text:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            parts = []
            for page in doc:
                parts.append(page.get_text())
            text = "\n".join(parts).strip()
            meta["pages"] = len(doc)
            meta["method"] = "pymupdf"
        except Exception as e:
            meta["pymupdf_error"] = str(e)

    if not text:
        return None, {**meta, "error": "no_text_extracted"}
    
    return text[:120_000], meta


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
