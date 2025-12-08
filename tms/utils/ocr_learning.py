# tms/utils/ocr_learning.py

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import frappe


def _get_template(document_type: str, country: str | None) -> Optional[Dict[str, Any]]:
    """Fetch one OCR Document Template for (document_type, country) or fallback by doc type only."""
    filters = {"document_type": document_type}
    if country:
        filters["country"] = country

    templates = frappe.get_all(
        "OCR Document Template",
        filters=filters,
        fields=[
            "name",
            "document_type",
            "country",
            "mrz_present",
            "mrz_pattern",
            "parse_instructions",
            "name_hints",
            "id_patterns_json",
            "forbidden_tokens",
            "raw_sample_text",
        ],
        limit=1,
    )
    return templates[0] if templates else None


def _get_examples(
    document_type: str,
    country: str | None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Fetch last few approved training examples for few-shot prompting."""
    filters = {"document_type": document_type, "status": "Approved"}
    if country:
        filters["country"] = country

    rows = frappe.get_all(
        "OCR Training Example",
        filters=filters,
        fields=[
            "name",
            "document_type",
            "country",
            "raw_text",
            "mrz_block",
            "full_name_correct",
            "id_no_correct",
            "nationality_correct",
        ],
        order_by="modified desc",
        limit=limit,
    )
    return rows or []


def _format_examples_for_prompt(examples: List[Dict[str, Any]]) -> str:
    """Format training examples into a prompt-friendly string."""
    if not examples:
        return "No previous examples available."

    parts: List[str] = []
    for ex in examples:
        parts.append(
            (
                "Example:\n"
                f"- Document Type: {ex.get('document_type')}\n"
                f"- Country: {ex.get('country')}\n"
                f"- Raw Text (truncated): { (ex.get('raw_text') or '')[:400] }\n"
                f"- Correct Full Name: {ex.get('full_name_correct')}\n"
                f"- Correct ID No: {ex.get('id_no_correct')}\n"
                f"- Correct Nationality: {ex.get('nationality_correct')}\n"
            )
        )
    return "\n\n".join(parts)


def _build_prompt(
    ocr_text: str,
    document_type: str,
    country: str | None,
    template: Optional[Dict[str, Any]],
    examples: List[Dict[str, Any]],
) -> str:
    """Create plain text prompt (we'll use a simple Chat model)."""
    template_instructions = ""
    name_hints = ""
    id_patterns = ""
    forbidden_tokens = ""

    if template:
        template_instructions = template.get("parse_instructions") or ""
        name_hints = template.get("name_hints") or ""
        forbidden_tokens = template.get("forbidden_tokens") or ""

        id_json = template.get("id_patterns_json") or ""
        try:
            patterns = json.loads(id_json) if id_json.strip() else []
            if isinstance(patterns, list):
                id_patterns = "\n".join(patterns)
        except Exception:
            id_patterns = id_json

    examples_block = _format_examples_for_prompt(examples)

    prompt = f"""
You are an ID document parsing assistant for a transport booking system.

- Your job is to extract:
  - full_name: Passenger full name
  - id_no: Passport / Iqama / Visa / National ID number
  - nationality: Country name in English
- Document Type: {document_type}
- Country: {country or "Unknown"}

Template instructions:
{template_instructions}

Name hints (words near the name field):
{name_hints}

ID patterns (regex or descriptions):
{id_patterns}

Tokens that must NOT be returned as id_no (ignore if they look like IDs):
{forbidden_tokens}

Previous approved examples from this system:
{examples_block}

Now parse the following OCR text (it may contain noise, MRZ lines, Arabic/English mix).
OCR TEXT:
----------------
{ocr_text}
----------------

Respond ONLY with a valid JSON object, no commentary.
Schema:
{{
  "full_name": "string",
  "id_no": "string",
  "nationality": "string"
}}

Rules:
- Do NOT hallucinate data that is not present.
- If you're unsure of a field, set it to empty string "".
- Prefer ID-like strings (with digits) over generic words like GOVERNMENT, KINGDOM, REPUBLIC.
"""
    return prompt


def refine_with_llm(
    ocr_text: str,
    document_type: str = "GenericID",
    country: str | None = None,
    model_name: str | None = None,
) -> Dict[str, Any]:
    """
    Use LangChain + an LLM (OpenAI or compatible) to refine parsed fields.

    Returns:
      {
        "full_name": str,
        "id_no": str,
        "nationality": str,
        "confidence": int (0-100),
        "engine": "llm"
      }
    """
    result = {
        "full_name": "",
        "id_no": "",
        "nationality": "",
        "confidence": 0,
        "engine": "llm",
    }

    if not ocr_text or not ocr_text.strip():
        return result

    # Import LangChain lazily so your site still runs if it's not installed.
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        frappe.log_error(
            "LangChain or langchain_openai not installed",
            "OCR Learning / refine_with_llm",
        )
        return result

    # 1) Fetch template + examples from Frappe
    template = _get_template(document_type, country)
    examples = _get_examples(document_type, country, limit=3)

    # 2) Build prompt
    prompt_text = _build_prompt(ocr_text, document_type, country, template, examples)
    prompt = ChatPromptTemplate.from_template("{input}")

    # 3) LLM setup (OpenAI by default; you can later swap to DeepSeek/local)
    if not model_name:
        model_name = "gpt-4.1-mini"

    llm = ChatOpenAI(
        model=model_name,
        temperature=0,
    )

    chain = prompt | llm  # simple chain: prompt -> chat completion

    try:
        response = chain.invoke({"input": prompt_text})
        content = response.content

        # content should be JSON, but we still parse defensively
        if isinstance(content, str):
            raw = content
        else:
            # some LangChain models may return list[HumanMessage/AIMessage], etc.
            raw = str(content)

        # Try direct JSON parse
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            # Try to find JSON blob inside text
            import re

            m = re.search(r"\{.*\}", raw, flags=re.S)
            if m:
                data = json.loads(m.group(0))

        if not isinstance(data, dict):
            return result

        full_name = (data.get("full_name") or "").strip()
        id_no = (data.get("id_no") or "").strip()
        nationality = (data.get("nationality") or "").strip()

        # naive confidence
        confidence = 0
        if full_name:
            confidence += 40
        if id_no:
            confidence += 40
        if nationality:
            confidence += 20

        result.update(
            {
                "full_name": full_name,
                "id_no": id_no,
                "nationality": nationality,
                "confidence": min(confidence, 100),
                "engine": "llm",
            }
        )
        return result

    except Exception as e:
        frappe.log_error(
            f"LLM refinement failed: {e}",
            "OCR Learning / refine_with_llm",
        )
        return result
