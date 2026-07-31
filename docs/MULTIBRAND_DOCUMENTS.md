# Multi-Brand Legal Profiles & Documents

## Discovery: what existed before this work

An audit of the codebase (contracts, invoices, quotations, receipts, PDF
generation, print views, logos, signatures, document numbers, templates) found:

> **No document-generation system existed.** There were no invoice/contract/
> receipt/quotation models, no PDF generation, no print views, no logo or
> signature handling, and no document numbering anywhere in the repository.

This work therefore builds the **legal-entity, brand-profile, signatory,
numbering, snapshot, and asset foundation** plus the administrator configuration
screens and a brand-aware document generator. **It does not fabricate legal
templates or wording.** The actual invoice/contract PDF **layout templates**
remain to be designed with the business (see "Remaining" below).

## Business structure

Three **presentation brands** over two **legal profiles**:

| Brand (`key`) | Prefix | Legal profile |
| --- | --- | --- |
| Fuel Dezign (`fuel_dezign`) | `FUEL` | Fuel (`fuel`) |
| Morph Studio (`morph_studio`) | `MORPH-STUDIO` | Morph (`morph`) — shared |
| Morph Solutions (`morph_solutions`) | `MORPH-SOLUTIONS` | Morph (`morph`) — shared |

Morph Studio and Morph Solutions **share one legal profile** (legal name,
registration, tax, address, contact, bank details, owner name/title/signature,
legal terms) but keep their **own** display name, logo, accent colors, website,
public email, service category, and document prefix.

The seed migration creates this structure only. Registration numbers, tax
numbers, bank details, owner names/titles, signatures, and legal terms are left
**blank** for an admin to fill in on the Brand Profiles screen — **nothing legal
is invented**.

## Models

- `LegalEntity` — the legal profile (Fuel, shared Morph).
- `BrandProfile` — a presentation brand → points at a legal entity.
- `Signatory` — a named signatory + signature image (per legal entity).
- `DocumentSequence` — per (legal entity + document type + year) counter.
- `GeneratedDocument` — an issued document (unique `document_number`).
- `GeneratedDocumentSnapshot` — the immutable frozen values (see below).

Only admins may manage legal entities, brands, and signatories
(`/api/legal-entities/`, `/api/brands/`, `/api/signatories/`). Brands are
readable by all authenticated users so the document brand selector can list them.

## Dynamic brand selection

`POST /api/documents/generate/` takes a `brand`, a `document_type`
(invoice / contract / receipt / quotation / payment_acknowledgment), and optional
client / deal / amount / currency / terms. The selected brand controls the logo,
display + legal name, colors, address, contact, registration/tax details, bank
info, signatory + signature, terms, footer, document-number prefix, and PDF
filename.

## Immutable historical snapshots

Every generated document stores a `GeneratedDocumentSnapshot` capturing the exact
values used at generation time (brand key + name, legal entity key + legal name,
registration, tax, address, contact, bank details, accent color, prefix, logo
reference + hash, signatory name/title + signature reference + hash, terms,
document number + type, client, amount, currency, timestamp, generating user,
template version) plus a full JSON `data` blob.

**Editing a brand or legal entity later never changes past documents.** Existing
Fuel documents stay Fuel documents forever, even if the brand is renamed or its
legal entity is reassigned. This is covered by automated tests.

## Numbering

Concurrency-safe: the sequence row is locked (`select_for_update`) inside the
generation transaction; the final `document_number` has a **unique** constraint,
guaranteeing global uniqueness. The two Morph brands **share** a legal sequence
(they share a legal entity) while showing different visible prefixes:

```
FUEL-INV-2026-0012
MORPH-STUDIO-INV-2026-0013
MORPH-SOLUTIONS-CON-2026-0014
```

## Assets (logos & signatures)

Uploaded via `POST /api/brands/{id}/logo/` and `POST /api/signatories/{id}/signature/`.
Validation: allowed extension (PNG/JPG/WebP), content-type, real image decode
(Pillow), max dimensions and bytes, safe filename, **SVG rejected**, no
executable content. A SHA-256 hash of the asset is stored (and snapshotted).

- **Development** — local filesystem storage under `MEDIA_ROOT`.
- **Production** — do **not** rely on an ephemeral container filesystem. Mount
  persistent storage or configure an object-storage backend. Object-storage
  verification is **pending** (no service-role credentials were available, and
  service-role credentials must never be exposed to React).

## Remaining / not claimed complete

- The **visual PDF templates** (invoice/contract/receipt layouts, wording) are
  **not** implemented — they require the real legal content and design from the
  business. The generator records a structured, snapshotted document; rendering a
  branded PDF from the snapshot is the next step.
- **Real legal identifiers** (registration, tax, bank, owner, signatures, terms)
  must be entered by an admin before any document is issued for real use.
- **Production object storage** for assets is documented but unverified.
