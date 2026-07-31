"""Excel (.xlsx) lead import: parsing, validation, and de-duplication.

The importer is defensive by design — it never silently drops or duplicates
rows. Every row is classified as imported, invalid, duplicate, or skipped, and
the counts are returned to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from .models import Lead
from .phone import normalize_phone

# Accepted header aliases (lower-cased, stripped). Documented, not guessed.
NAME_ALIASES = {"name", "full name", "lead name", "customer", "customer name", "client", "contact", "contact name", "الاسم", "اسم"}
PHONE_ALIASES = {"phone", "phone number", "mobile", "mobile number", "number", "tel", "telephone", "whatsapp", "الهاتف", "رقم", "رقم الهاتف", "الجوال"}

MAX_ROWS = getattr(settings, "LEAD_IMPORT_MAX_ROWS", 5000)


@dataclass
class RowError:
    row: int
    reason: str


@dataclass
class ImportResult:
    total_rows: int = 0
    imported: list = field(default_factory=list)  # list of dicts ready to create
    invalid: list = field(default_factory=list)  # RowError
    duplicates: list = field(default_factory=list)  # RowError
    skipped: list = field(default_factory=list)  # RowError

    def counts(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "imported": len(self.imported),
            "invalid": len(self.invalid),
            "duplicate": len(self.duplicates),
            "skipped": len(self.skipped),
        }

    def summary(self) -> dict:
        return {
            **self.counts(),
            "invalid_rows": [e.__dict__ for e in self.invalid[:100]],
            "duplicate_rows": [e.__dict__ for e in self.duplicates[:100]],
            "skipped_rows": [e.__dict__ for e in self.skipped[:100]],
        }


class ImportError_(Exception):
    """Workbook-level failure (not a per-row problem)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _match_header(header_cells):
    """Return (name_index, phone_index) or raise ImportError_ on missing headers."""
    name_idx = phone_idx = None
    for idx, cell in enumerate(header_cells):
        value = (str(cell).strip().lower()) if cell is not None else ""
        if name_idx is None and value in NAME_ALIASES:
            name_idx = idx
        if phone_idx is None and value in PHONE_ALIASES:
            phone_idx = idx
    if name_idx is None or phone_idx is None:
        missing = []
        if name_idx is None:
            missing.append("name")
        if phone_idx is None:
            missing.append("phone")
        raise ImportError_(
            "missing_headers",
            f"Required column(s) not found: {', '.join(missing)}. "
            f"Expected a 'Name' and a 'Phone' header on the first row.",
        )
    return name_idx, phone_idx


def parse_workbook(file_obj, *, default_region: str = "JO") -> ImportResult:
    """Parse an .xlsx file into an :class:`ImportResult`.

    De-duplicates within the file and against existing leads by normalized
    phone. ``file_obj`` is any binary file-like object.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - openpyxl is a hard dep
        raise ImportError_("openpyxl_missing", f"openpyxl is required: {exc}")

    try:
        # data_only=True returns cached formula values instead of formula text.
        workbook = load_workbook(file_obj, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - malformed workbook
        raise ImportError_("bad_workbook", f"Could not read the spreadsheet: {type(exc).__name__}.")

    worksheet = workbook.active
    result = ImportResult()

    rows = worksheet.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        raise ImportError_("empty_workbook", "The spreadsheet has no rows.")

    name_idx, phone_idx = _match_header(list(header))

    seen_phones: set[str] = set()
    existing = set(
        Lead.objects.exclude(normalized_phone="").values_list("normalized_phone", flat=True)
    )

    row_number = 1  # header was row 1
    for raw_row in rows:
        row_number += 1
        if result.total_rows >= MAX_ROWS:
            raise ImportError_(
                "too_many_rows",
                f"This file exceeds the maximum of {MAX_ROWS} rows.",
            )

        cells = list(raw_row)
        name_value = cells[name_idx] if name_idx < len(cells) else None
        phone_value = cells[phone_idx] if phone_idx < len(cells) else None

        name = str(name_value).strip() if name_value is not None else ""
        phone_raw = str(phone_value).strip() if phone_value is not None else ""

        # Entirely empty row -> skipped, not an error.
        if not name and not phone_raw:
            continue

        result.total_rows += 1

        # Formula leakage guard: iter_rows with data_only returns None for
        # uncached formulas; a literal starting with '=' means a formula string.
        if phone_raw.startswith("=") or name.startswith("="):
            result.invalid.append(RowError(row_number, "Formula cell not allowed."))
            continue

        if not name:
            result.invalid.append(RowError(row_number, "Missing name."))
            continue

        normalized, country = normalize_phone(phone_raw, default_region=default_region)
        if not normalized:
            result.invalid.append(RowError(row_number, f"Invalid phone: '{phone_raw}'."))
            continue

        if normalized in seen_phones:
            result.duplicates.append(RowError(row_number, f"Duplicate within file: {normalized}."))
            continue
        if normalized in existing:
            result.duplicates.append(RowError(row_number, f"Already exists in CRM: {normalized}."))
            seen_phones.add(normalized)
            continue

        seen_phones.add(normalized)
        result.imported.append(
            {
                "name": name,
                "original_phone": phone_raw,
                "normalized_phone": normalized,
                "country_context": country,
            }
        )

    workbook.close()
    return result
