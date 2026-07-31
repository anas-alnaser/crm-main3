"""Phone-number normalization for lead deduplication.

Focused on Jordanian numbers (default region) with sane handling of common
international formats. Deliberately dependency-free: it normalizes to E.164-ish
digits so two spellings of the same number collide, without pretending to be a
full libphonenumber validator.

Returns ``(normalized, country_context)``; ``normalized`` is empty when the
input can't be salvaged into a plausible number.
"""
from __future__ import annotations

import re

JORDAN_CC = "962"
# Jordan national numbers are 9 significant digits after the country code
# (mobile 7XXXXXXXX, most landlines 6XXXXXXX with an area digit). We keep the
# check permissive: 8–9 digits after the leading 0 is accepted.


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def normalize_phone(raw: str, default_region: str = "JO") -> tuple[str, str]:
    if raw is None:
        return "", ""
    original = raw.strip()
    if not original:
        return "", ""

    has_plus = original.strip().startswith("+")
    digits = _digits(original)
    if not digits:
        return "", ""

    # International prefix "00" -> treat as "+".
    if digits.startswith("00"):
        digits = digits[2:]
        has_plus = True

    if has_plus:
        return _finalize_international(digits)

    # Already includes the Jordan country code without '+'.
    if digits.startswith(JORDAN_CC) and len(digits) >= 11:
        return _finalize_international(digits)

    # National format with a trunk '0' (e.g. 079..., 06...).
    if default_region == "JO":
        national = digits.lstrip("0")
        if 8 <= len(national) <= 9:
            return f"+{JORDAN_CC}{national}", "JO"
        # Fallback: keep digits as-is with the country code.
        if national:
            return f"+{JORDAN_CC}{national}", "JO"

    return _finalize_international(digits)


def _finalize_international(digits: str) -> tuple[str, str]:
    if not digits:
        return "", ""
    country = "JO" if digits.startswith(JORDAN_CC) else ""
    return f"+{digits}", country
