from __future__ import annotations

import os
from typing import Any, Literal

import google.generativeai as genai
from openai import AsyncOpenAI


async def chat_completion(
    prompt: str,
    system_instruction: str | None = None,
    model: str | None = None,
    response_format: Literal["text", "json_object"] = "text",
) -> str:
    """
    Generic async wrapper for LLM completions.
    Supports GEMINI_API_KEY (default) or OPENAI_API_KEY.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not gemini_key and not openai_key:
        return "LLM_NOT_CONFIGURED: Please set GEMINI_API_KEY or OPENAI_API_KEY in .env"

    if gemini_key:
        return await _call_gemini(prompt, system_instruction, model, response_format)
    else:
        return await _call_openai(prompt, system_instruction, model, response_format)


async def _call_gemini(
    prompt: str,
    system_instruction: str | None = None,
    model: str | None = None,
    response_format: str = "text",
) -> str:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model_name = model or "gemini-1.5-flash"
    
    m = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction,
    )
    
    generation_config = {}
    if response_format == "json_object":
        generation_config["response_mime_type"] = "application/json"

    response = await m.generate_content_async(
        prompt,
        generation_config=genai.types.GenerationConfig(**generation_config)
    )
    return response.text


async def _call_openai(
    prompt: str,
    system_instruction: str | None = None,
    model: str | None = None,
    response_format: str = "text",
) -> str:
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model_name = model or "gpt-4o-mini"
    
    messages: list[dict[str, Any]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    
    response = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        response_format={"type": "json_object"} if response_format == "json_object" else {"type": "text"},
    )
    return response.choices[0].message.content or ""
