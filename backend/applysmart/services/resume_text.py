from __future__ import annotations

from io import BytesIO
from typing import Any

# Lazy-import PDF stacks: top-level imports crash many serverless runtimes (e.g. Vercel)
# when native wheels or system libs are missing; the API must still boot.


def _load_pdfplumber():
    try:
        import pdfplumber

        return pdfplumber
    except Exception:
        # ImportError, missing native deps on serverless, etc.
        return None


def _load_fitz():
    try:
        import fitz  # PyMuPDF

        return fitz
    except Exception:
        return None


def extract_text_from_pdf(data: bytes) -> tuple[str | None, dict[str, Any]]:
    meta: dict[str, Any] = {"bytes": len(data)}
    text = ""

    pdfplumber = _load_pdfplumber()
    fitz = _load_fitz()

    # Strategy 1: pdfplumber (best for structured resumes)
    if pdfplumber is None:
        meta["pdfplumber_error"] = "pdfplumber_unavailable"
    else:
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
        if fitz is None:
            meta["pymupdf_error"] = "pymupdf_unavailable"
        else:
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
