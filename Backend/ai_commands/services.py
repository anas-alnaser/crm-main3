import json
import os
import re
import ssl
import urllib.error
import urllib.request

import certifi
from django.utils import timezone


ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
SUPPORTED_INTENTS = {
    "create_meeting",
    "create_task",
    "log_activity",
    "move_deal",
    "create_deal",
    "create_company",
    "add_note",
    "schedule_followup",
    "update_deal_value",
    "update_deal_close_date",
    "reassign_deal_owner",
    "edit_company_details",
    "edit_meeting",
    "update_task",
    "delete_record",
    "delete_deal",
    "delete_company",
    "delete_task",
    "delete_meeting",
    "change_commission_rate",
    "change_user_role",
    "create_user",
    "deactivate_user",
    "bulk_operation",
}


class AICommandError(Exception):
    pass


class MissingAIKeyError(AICommandError):
    pass


def strip_code_fences(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_ai_json(text):
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise AICommandError("AI response did not contain JSON.")
        return json.loads(match.group(0))


def normalize_draft(draft):
    intent = draft.get("intent")
    fields = draft.get("fields") if isinstance(draft.get("fields"), dict) else {}
    confidence = draft.get("confidence", 0)
    missing = draft.get("missing") if isinstance(draft.get("missing"), list) else []
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0

    if intent not in SUPPORTED_INTENTS:
        missing = sorted(set([*missing, "intent"]))

    return {
        "intent": intent,
        "fields": fields,
        "confidence": max(0, min(1, confidence)),
        "missing": missing,
    }


def build_prompt(text):
    today = timezone.localdate().isoformat()
    return f"""
You interpret commands for a private sales CRM. Today is {today}.

Return ONLY valid JSON. No prose. No markdown. No code fences.

Allowed intents:
- Tier 1 auto if confident and fully resolved: create_meeting, create_task, log_activity, move_deal, create_deal, create_company, add_note, schedule_followup
- Tier 2 confirmation required: update_deal_value, update_deal_close_date, reassign_deal_owner, edit_company_details, edit_meeting, update_task
- Tier 3 blocked/refused: delete_record, delete_deal, delete_company, delete_task, delete_meeting, change_commission_rate, change_user_role, create_user, deactivate_user, bulk_operation

Schema:
{{
  "intent": one of the allowed intents,
  "fields": {{
    "title": string,
    "company_name": string,
    "deal_identifier": string,
    "task_identifier": string,
    "meeting_identifier": string,
    "owner_username": string,
    "target_stage": string,
    "value": number,
    "currency": string,
    "expected_close_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD",
    "status": string,
    "activity_type": "call" | "meeting" | "email" | "note",
    "contact_person": string,
    "email": string,
    "phone": string,
    "country": string,
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM",
    "end_time": "HH:MM" | null,
    "location": string | null,
    "notes": string | null,
    "content": string
  }},
  "confidence": number between 0 and 1,
  "missing": []
}}

Include only fields relevant to the intent. For destructive, system, user, permissions, role, commission-rate, or bulk/all-records requests, choose the matching Tier 3 blocked intent.
Interpret relative dates like "tomorrow" and "next Sunday" relative to {today}.
If the year is omitted, choose the nearest future date.
If required information is missing or ambiguous, include it in missing and lower confidence.

Command: {text}
""".strip()


def call_anthropic(prompt):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise MissingAIKeyError("ANTHROPIC_API_KEY is not configured.")

    body = json.dumps(
        {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 500,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ANTHROPIC_URL,
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise AICommandError(f"AI provider request failed: {exc}") from exc

    content = payload.get("content") or []
    if not content or "text" not in content[0]:
        raise AICommandError("AI provider returned an unexpected response.")
    return content[0]["text"]


def interpret_command(text, user):
    del user
    response_text = call_anthropic(build_prompt(text))
    return normalize_draft(parse_ai_json(response_text))
