from __future__ import annotations

import re
from collections import Counter

_KNOWN_LANGS = [
    "python",
    "javascript",
    "typescript",
    "java",
    "c++",
    "cpp",
    "c#",
    "csharp",
    "go",
    "rust",
    "kotlin",
    "swift",
    "ruby",
    "php",
    "r",
    "matlab",
    "scala",
    "dart",
    "sql",
    "html",
    "css",
    "bash",
    "shell",
]


def extract_languages_from_text(text: str, *, max_lang: int = 20) -> list[str]:
    t = text.lower()
    found: Counter[str] = Counter()
    for lang in _KNOWN_LANGS:
        if lang == "cpp":
            pattern = r"\bc\+\+\b"
        elif lang == "csharp":
            pattern = r"\bc#\b"
        else:
            pattern = r"\b" + re.escape(lang) + r"\b"
        if re.search(pattern, t):
            norm = "C++" if lang == "cpp" else ("C#" if lang == "csharp" else lang.title())
            found[norm] += 1
    # stable: by frequency then name
    return [k for k, _ in sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))][:max_lang]


def extract_resume_bullets(text: str, *, max_items: int = 12) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("-", "•", "*")):
            s = re.sub(r"^[-•*]\s*", "", s)
            if 10 < len(s) < 240:
                bullets.append(s)
        if len(bullets) >= max_items:
            break
    return bullets
