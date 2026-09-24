"""Direct Anthropic API helpers — no Emergent LLM proxy."""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from typing import AsyncIterator, Optional, Union

from anthropic import AsyncAnthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or ""
# Default Sonnet model — see current IDs at https://docs.anthropic.com/en/docs/about-claude/models/overview
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
# Cheaper/faster model for high-volume grounded report read/summarize + digest combine.
ANTHROPIC_MODEL_FAST = os.environ.get("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5")

# System prompt for messages.create / messages.stream: plain string or content-block list
# (list form enables Anthropic prompt caching via cache_control on a text block).
SystemPrompt = Union[str, list]

_EXTRACT_SYSTEM = """You extract financial data from bills, receipts, and invoices.
Return ONLY strict JSON with no markdown and no prose.

If the document is clearly NOT a bill, receipt, or invoice (e.g. resume, contract, marketing flyer, letter), return:
{"error": "not_financial"}

Otherwise return:
{"type": "revenue"|"expense", "category": string, "name": string, "amount": number, "month": "YYYY-MM", "vendor": string, "note": string, "confidence": "high"|"medium"|"low"}

Rules:
- type is usually "expense" for bills/invoices you pay; use "revenue" only for incoming invoices you issued.
- amount is the total in USD (number only, no currency symbols).
- month is the invoice/bill date as YYYY-MM when possible; otherwise best estimate.
- category is a grouping label like Payroll, Cloud/Infra, Sales & Mktg, G&A, Subscriptions — not the specific purchase.
- name is the specific line-item label (e.g. "MongoDB Database Subscription", "Render Hosting"). Prefer vendor + product/service when both are on the document. Do not copy category into name unless nothing more specific exists.
- vendor is the payee or issuer name.
- Do not guess amounts or dates — use confidence "low" when uncertain.
"""

# Workspace missing-vs-zero does not apply to extract_with_claude: the model reads
# document bytes, not Trenston fields. Unreadable amounts already fail closed
# (do-not-guess + unparseable_amount).

_client: Optional[AsyncAnthropic] = None


def anthropic_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)


def get_client() -> AsyncAnthropic:
    global _client
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


async def complete(system: SystemPrompt, user: str, *, max_tokens: int = 1200, model: Optional[str] = None) -> str:
    client = get_client()
    msg = await client.messages.create(
        model=model or ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts = []
    for block in msg.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()


async def stream_text(
    system: SystemPrompt,
    user: Optional[str] = None,
    *,
    messages: Optional[list[dict]] = None,
    max_tokens: int = 1600,
) -> AsyncIterator[str]:
    """Stream a completion. ``system`` may be a plain string or a list of
    Anthropic system content blocks (for prompt caching).

    Pass ``messages`` (alternating user/assistant, ending with user) for a
    multi-turn conversation; ``user`` alone keeps the single-turn behaviour.
    """
    if messages is None:
        if user is None:
            raise ValueError("stream_text needs user or messages")
        messages = [{"role": "user", "content": user}]
    client = get_client()
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            if text:
                yield text


def _parse_extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse model response as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Model response was not a JSON object")
    return data


_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
_MAX_LABEL_LEN = 100


def _coerce_label(value) -> str:
    if value is None:
        return ""
    return str(value).strip()[:_MAX_LABEL_LEN]


def _parse_positive_amount(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        return n if n > 0 else None
    cleaned = re.sub(r"[\s$,]", "", str(value).strip())
    if not cleaned:
        return None
    try:
        n = float(cleaned)
    except ValueError:
        return None
    return n if n > 0 else None


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _validate_extracted_financial(data: dict) -> dict:
    """Normalize and validate Claude extraction output for the entry form."""
    if data.get("error"):
        return data

    confidence = data.get("confidence")
    if confidence not in _VALID_CONFIDENCE:
        confidence = "medium"

    type_val = data.get("type")
    if type_val not in ("revenue", "expense"):
        type_val = "expense"
        confidence = "low"

    amount = _parse_positive_amount(data.get("amount"))
    if amount is None:
        return {"error": "unparseable_amount"}

    month = data.get("month")
    if not isinstance(month, str) or not _MONTH_RE.match(month.strip()):
        month = _current_month()
        confidence = "low"
    else:
        month = month.strip()

    category = _coerce_label(data.get("category"))
    vendor = _coerce_label(data.get("vendor"))
    name = _coerce_label(data.get("name")) or vendor or category
    out = {
        "type": type_val,
        "amount": round(amount, 2),
        "month": month,
        "category": category,
        "name": name,
        "vendor": vendor,
        "note": _coerce_label(data.get("note")),
        "confidence": confidence,
    }
    if data.get("engine"):
        out["engine"] = data.get("engine")
    return out


async def extract_with_claude(file_bytes: bytes, content_type: str) -> dict:
    if content_type == "application/pdf":
        block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(file_bytes).decode("ascii")},
        }
    elif content_type in ("image/png", "image/jpeg"):
        block = {
            "type": "image",
            "source": {"type": "base64", "media_type": content_type, "data": base64.standard_b64encode(file_bytes).decode("ascii")},
        }
    else:
        raise ValueError(f"Unsupported content type for extraction: {content_type}")

    client = get_client()
    msg = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=_EXTRACT_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                block,
                {"type": "text", "text": "Extract the financial transaction from this document."},
            ],
        }],
    )
    parts = []
    for block_out in msg.content:
        text = getattr(block_out, "text", None)
        if text:
            parts.append(text)
    raw = "".join(parts).strip()
    if not raw:
        raise ValueError("Empty response from model")
    out = _validate_extracted_financial(_parse_extract_json(raw))
    out["engine"] = "anthropic"
    return out


def extraction_configured() -> bool:
    try:
        import google_document_ai as docai
        return anthropic_configured() or docai.document_ai_configured()
    except Exception:
        return anthropic_configured()


async def extract_financial_document(
    file_bytes: bytes,
    content_type: str,
    *,
    use_document_ai: bool = True,
) -> dict:
    """Document AI first (GCP credits), Claude for low-confidence or missing parser.

    use_document_ai=False skips the GCP Invoice Parser (daily spend caps / kill switch).
    """
    docai_result = None
    if use_document_ai:
        try:
            import google_document_ai as docai
            docai_result = await docai.extract_invoice(file_bytes, content_type)
        except Exception:
            docai_result = None

    if docai_result and not docai_result.get("error") and docai_result.get("confidence") == "high":
        return _validate_extracted_financial(docai_result)

    if anthropic_configured():
        try:
            claude = await extract_with_claude(file_bytes, content_type)
            if claude.get("error") and docai_result and not docai_result.get("error"):
                return _validate_extracted_financial(docai_result)
            return claude
        except Exception:
            if docai_result and not docai_result.get("error"):
                return _validate_extracted_financial(docai_result)
            raise

    if docai_result:
        return docai_result if docai_result.get("error") else _validate_extracted_financial(docai_result)
    raise RuntimeError("No extraction engine configured")


_DECISION_DRAFT_SYSTEM = """You are Trenston, drafting a decision card for a CEO based on a real signal detected in their business data.
Return ONLY strict JSON with no markdown and no prose:
{"title": string, "description": string, "recommendation": string, "confidence": number, "category": string, "impact": "High"|"Medium"|"Low"}

Rules:
- Be specific. Cite the actual numbers, names, and dates from the signal. Do not write generically.
- Write plainly in title, description, and recommendation. Avoid em dashes. Prefer periods, commas, or plain connecting words instead, unless a sentence genuinely cannot be split any other way.
- confidence is your genuine estimate from 0-100 that this recommendation is the right call given the signal (integer).
- category is a short label like Finance, Sales, People, Product, Ops.
- impact reflects business urgency: High / Medium / Low.
- Company context may include unknown_fields and instructions_for_missing_data. Follow those instructions. Null financials are not zero. Do not claim $0 cash, 0 MRR, or that they are out of runway when those fields are unknown.
"""

_DELEGATE_DRAFT_SYSTEM = """You are Trenston, drafting a delegation card for a CEO based on a real operational signal.
Return ONLY strict JSON with no markdown and no prose:
{"title": string, "detail": string, "suggested_owner_user_id": string, "suggested_owner_name": string}

Rules:
- Be specific. Cite the task, person, and dates from the signal.
- Write plainly in title and detail. Avoid em dashes. Prefer periods, commas, or plain connecting words instead, unless a sentence genuinely cannot be split any other way.
- suggested_owner_user_id and suggested_owner_name MUST come from the signal context (assignee_user_id / assignee_name). Do not invent a person.
- title is a short actionable handoff; detail explains what to do and why.
- If company context lists unknown_fields, do not fill those gaps with invented numbers or a $0 default.
"""

_VALID_IMPACT = frozenset({"High", "Medium", "Low"})


def _validate_decision_draft(data: dict, signal: dict) -> dict:
    title = _coerce_label(data.get("title"))
    if not title:
        title = _coerce_label(signal.get("summary")) or "Review detected signal"
    description = str(data.get("description") or signal.get("detail") or "").strip()[:800]
    recommendation = str(data.get("recommendation") or "").strip()[:800]
    if not recommendation:
        recommendation = "Review the signal and choose a course of action."

    conf_raw = data.get("confidence")
    confidence = None
    confidence_unavailable = False
    try:
        if conf_raw is None or conf_raw == "":
            raise TypeError("missing")
        confidence = int(round(float(conf_raw)))
        confidence = max(0, min(100, confidence))
    except (TypeError, ValueError):
        # Never invent a percentage — surface that the model omitted a real estimate.
        confidence = None
        confidence_unavailable = True

    impact = data.get("impact")
    if impact not in _VALID_IMPACT:
        sev = (signal.get("severity") or "medium").lower()
        impact = {"high": "High", "medium": "Medium", "low": "Low"}.get(sev, "Medium")

    category = _coerce_label(data.get("category")) or _coerce_label(signal.get("category")) or "General"
    return {
        "title": title[:200],
        "description": description,
        "recommendation": recommendation,
        "confidence": confidence,
        "confidence_unavailable": confidence_unavailable,
        "category": category or "General",
        "impact": impact,
    }


def _validate_delegate_draft(data: dict, signal: dict) -> dict:
    title = _coerce_label(data.get("title"))
    if not title:
        title = _coerce_label(signal.get("summary")) or "Follow up on blocker"
    detail = str(data.get("detail") or signal.get("detail") or "").strip()[:800]
    # Owner must come from the signal — never invent
    owner_id = signal.get("assignee_user_id") or data.get("suggested_owner_user_id") or None
    owner_name = signal.get("assignee_name") or data.get("suggested_owner_name") or "Unassigned"
    owner_name = str(owner_name).strip()[:100] or "Unassigned"
    if owner_id is not None:
        owner_id = str(owner_id).strip() or None
    return {
        "title": title[:200],
        "detail": detail or title,
        "suggested_owner_user_id": owner_id,
        "suggested_owner_name": owner_name,
    }


async def draft_decision(signal: dict, company_context: dict) -> dict:
    """Draft a decision card from a detected signal. Returns validated fields."""
    user = (
        f"Company: {json.dumps(company_context, default=str)}\n"
        f"Signal: {json.dumps(signal, default=str)}\n"
        "Draft the decision card JSON now."
    )
    raw = await complete(_DECISION_DRAFT_SYSTEM, user, max_tokens=800)
    if not raw:
        raise ValueError("Empty response from model")
    return _validate_decision_draft(_parse_extract_json(raw), signal)


async def draft_delegate(signal: dict, company_context: dict) -> dict:
    """Draft a delegate card from a task/blocker signal. Returns validated fields."""
    user = (
        f"Company: {json.dumps(company_context, default=str)}\n"
        f"Signal: {json.dumps(signal, default=str)}\n"
        "Draft the delegate card JSON now. Use the signal's assignee_user_id and assignee_name as the owner."
    )
    raw = await complete(_DELEGATE_DRAFT_SYSTEM, user, max_tokens=600)
    if not raw:
        raise ValueError("Empty response from model")
    return _validate_delegate_draft(_parse_extract_json(raw), signal)


_REPORT_SUMMARY_SYSTEM = """You are Trenston, reading one business report on behalf of a CEO who receives many of these and cannot read each one in full.
Return ONLY strict JSON with no markdown and no prose:
{"summary": string, "key_figures": [{"label": string, "value": string}], "unclear": boolean}

Rules:
- summary is 2-4 sentences describing what this report shows, written in plain language, with real figures worked into the sentences rather than listed separately.
- Only state a number, date, or figure that appears literally in the report. Never invent, estimate, round significantly, or infer a figure that is not present.
- key_figures lists up to 8 notable labeled figures that appear in the report (empty list if none are clear).
- If the report's content is unclear, unreadable, or doesn't look like a business report at all, set unclear to true and say so plainly in summary rather than guessing at what it might mean.
- Write plainly. Avoid em dashes; use periods, commas, or plain connecting words instead, unless a sentence genuinely cannot be split any other way.
"""

_REPORTS_DIGEST_SYSTEM = """You are Trenston, combining several already-summarized business reports from the same day into one short briefing for a CEO.
Write 1-3 short paragraphs. Group related reports together where it makes sense (e.g. multiple reports about the same commodity or topic) rather than listing them one by one.
Only state a number, date, or figure that appears literally in the input summaries or key_figures. Never invent, average, or estimate a number that is not present. If two reports appear to conflict, say so rather than picking one silently. Write plainly; avoid em dashes unless a sentence genuinely cannot be split any other way.
Return plain prose only — no JSON, no markdown headings, no bullet lists.
"""


def _validate_report_summary(data: dict) -> dict:
    summary = str(data.get("summary") or "").strip()[:2000]
    unclear = bool(data.get("unclear"))
    if not summary:
        summary = "This file could not be summarized clearly."
        unclear = True
    figures = []
    raw_figs = data.get("key_figures") or []
    if isinstance(raw_figs, list):
        for item in raw_figs[:8]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()[:120]
            value = str(item.get("value") or "").strip()[:120]
            if label and value:
                figures.append({"label": label, "value": value})
    return {"summary": summary, "key_figures": figures, "unclear": unclear}


async def summarize_report_document(
    content: bytes | str,
    content_type: str,
    filename: str,
    *,
    truncated: bool = False,
) -> dict:
    """Summarize one uploaded report. PDF/images use multimodal blocks; sheets use text."""
    if not anthropic_configured():
        raise RuntimeError("AI summarization is not configured")

    client = get_client()
    name = (filename or "report").strip()[:200] or "report"
    note = (
        "Note: this spreadsheet was truncated to fit the model context. "
        "Only summarize what is present below.\n\n"
        if truncated
        else ""
    )

    if content_type == "application/pdf":
        if not isinstance(content, (bytes, bytearray)):
            raise ValueError("PDF content must be bytes")
        user_content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(content).decode("ascii"),
                },
            },
            {
                "type": "text",
                "text": f"{note}Filename: {name}\nSummarize this business report as JSON now.",
            },
        ]
    elif content_type in ("image/png", "image/jpeg"):
        if not isinstance(content, (bytes, bytearray)):
            raise ValueError("Image content must be bytes")
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": base64.standard_b64encode(content).decode("ascii"),
                },
            },
            {
                "type": "text",
                "text": f"{note}Filename: {name}\nSummarize this business report as JSON now.",
            },
        ]
    else:
        text = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
        user_content = (
            f"{note}Filename: {name}\nContent type: {content_type}\n\n"
            f"Report contents:\n{text}\n\nSummarize this business report as JSON now."
        )

    msg = await client.messages.create(
        model=ANTHROPIC_MODEL_FAST,
        max_tokens=1200,
        system=_REPORT_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    parts = []
    for block_out in msg.content:
        text = getattr(block_out, "text", None)
        if text:
            parts.append(text)
    raw = "".join(parts).strip()
    if not raw:
        raise ValueError("Empty response from model")
    out = _validate_report_summary(_parse_extract_json(raw))
    if truncated and not out["unclear"]:
        out["summary"] = (
            out["summary"].rstrip()
            + " Some rows were omitted because the file was large."
        )
    return out


async def combine_daily_report_digest(items: list[dict]) -> str:
    """Combine already-summarized reports for one day into connected prose."""
    if not items:
        return ""
    if len(items) == 1:
        return str(items[0].get("summary") or "").strip()
    if not anthropic_configured():
        # Fallback: join summaries plainly when AI is down
        return "\n\n".join(
            str(it.get("summary") or "").strip() for it in items if it.get("summary")
        )
    payload = []
    for it in items:
        payload.append({
            "filename": it.get("filename") or "report",
            "summary": it.get("summary") or "",
            "key_figures": it.get("key_figures") or [],
            "unclear": bool(it.get("unclear")),
        })
    user = (
        "Today's already-summarized reports (JSON):\n"
        f"{json.dumps(payload, default=str)}\n\n"
        "Write the combined daily briefing now."
    )
    text = await complete(
        _REPORTS_DIGEST_SYSTEM, user, max_tokens=900, model=ANTHROPIC_MODEL_FAST,
    )
    return _strip_markdown_fences(text or "").strip()


GMAIL_DRAFT_DISCLAIMER = "(Drafted in Trenston. Edit this in Gmail before you send.)"

_GMAIL_REPLY_SYSTEM = """You draft short professional email replies for a CEO using Trenston.
Return ONLY the email body as plain text — no subject line, no markdown fences, no preamble.

Rules:
- Keep it concise (about 4–8 sentences). Sound like a real operator, not a chatbot.
- When a snippet/preview is provided, reply to that substance specifically.
- When no snippet is provided, write a brief general follow-up based only on the subject.
  Do NOT invent what the other person said, asked, agreed to, or promised.
- Do not invent facts, commitments, dates, numbers, or meeting details absent from the context.
- Sign off with "[your name]" — never invent the sender's real name.
- Do not include email headers (To/Subject/From).
"""


def fallback_gmail_draft_body(*, subject: str = "", snippet: str = "") -> str:
    """Template used when AI is unavailable — never invents conversation details."""
    subject = (subject or "").strip()
    snippet = (snippet or "").strip()
    parts = ["Hi,", "", GMAIL_DRAFT_DISCLAIMER, ""]
    if snippet:
        parts.extend(["On their last note:", snippet, ""])
    elif subject:
        parts.extend([f"Following up on: {subject}", ""])
    return "\n".join(parts).rstrip() + "\n"


def _strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned


async def draft_gmail_reply(*, subject: str = "", to_email: str = "", snippet: str = "") -> str:
    """AI-written Gmail reply body with Trenston disclaimer. Falls back on any AI failure."""
    subject = (subject or "").strip()[:200]
    to_email = (to_email or "").strip()[:200]
    snippet = (snippet or "").strip()[:500]
    if not anthropic_configured():
        return fallback_gmail_draft_body(subject=subject, snippet=snippet)
    preview = snippet if snippet else "(none — no preview available; do not invent conversation details)"
    user = (
        f"Subject: {subject or '(none)'}\n"
        f"From: {to_email or '(unknown)'}\n"
        f"Snippet/preview:\n{preview}\n\n"
        "Draft the reply body now."
    )
    try:
        text = await complete(_GMAIL_REPLY_SYSTEM, user, max_tokens=500)
    except Exception:
        return fallback_gmail_draft_body(subject=subject, snippet=snippet)
    text = _strip_markdown_fences(text or "")
    if not text:
        return fallback_gmail_draft_body(subject=subject, snippet=snippet)
    if GMAIL_DRAFT_DISCLAIMER not in text:
        text = f"{text.rstrip()}\n\n{GMAIL_DRAFT_DISCLAIMER}"
    return text.rstrip() + "\n"
