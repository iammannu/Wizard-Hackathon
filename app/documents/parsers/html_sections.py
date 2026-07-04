"""
HTML/XBRL filing -> plaintext + structured sections.

Approach and its honest limits:
  Modern SEC filings are inline-XBRL HTML with heavy markup. We strip
  script/style/XBRL-hidden nodes and walk the remaining block-level elements
  (p, div, span, h1-h6, td) in document order, treating any short line
  (<120 chars) that starts with "Item <number>[letter]." as a section
  boundary. Everything between boundaries accumulates into that section's
  text; anything before the first recognized header goes into "_preamble".

  This deliberately does not attempt XBRL-tag-aware structured extraction
  (which SEC's own facts API could eventually provide more precisely — a
  real future upgrade, not built here). It also does not attempt to parse
  DEF 14A / press-release / transcript structure, which don't follow the
  Item-numbering convention — those fall back to a single "_full_text"
  section via parse_generic_html(), which every non-Item-numbered doc type
  should use instead of parse_filing_sections().

  Known failure mode this handles: a filing's table of contents repeats
  every Item header as a short line near the top, with little or no content
  before the next TOC entry. Since a header re-occurring resets that
  section's accumulated text (see the loop below), the near-empty TOC
  capture is naturally overwritten once the real section appears later in
  the document — no separate TOC-detection logic needed.
"""
import re
from bs4 import BeautifulSoup

# Matches both 10-K/10-Q style headers ("Item 1A. Risk Factors") and 8-K
# style decimal sub-item headers ("Item 1.01 Entry into a Material Agreement").
_ITEM_HEADER_RE = re.compile(r"^item\s+(\d{1,2}(?:\.\d{2})?[a-c]?)\.?\s*[-–:]?\s*(.{0,100})$", re.IGNORECASE)
_BLOCK_TAGS = ["p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6", "td", "li"]
_MAX_HEADER_LINE_LEN = 120


def _clean_text(raw_html: str) -> BeautifulSoup:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "ix:header", "head"]):
        tag.decompose()
    return soup


def parse_generic_html(raw_html: str) -> dict:
    """For document types with no reliable Item-style structure (DEF 14A,
    press releases, IR pages, transcripts). Returns {"_full_text": "..."}."""
    soup = _clean_text(raw_html)
    text = _normalize_whitespace(soup.get_text(separator="\n"))
    return {"_full_text": text} if text else {}


def parse_filing_sections(raw_html: str) -> dict:
    """For 10-K/10-Q/8-K style filings that use "Item N." section numbering.
    Returns {section_key: section_text}, e.g. {"item_1a": "...", "item_7": "..."}."""
    soup = _clean_text(raw_html)

    lines: list[str] = []
    for element in soup.find_all(_BLOCK_TAGS):
        # Only leaf-ish elements — skip containers whose text is just the
        # concatenation of children we'll visit separately.
        if element.find(_BLOCK_TAGS):
            continue
        text = _normalize_whitespace(element.get_text(separator=" "))
        if text:
            lines.append(text)

    sections: dict[str, str] = {}
    current_key = "_preamble"
    buffer: list[str] = []

    def flush():
        text = _normalize_whitespace("\n".join(buffer))
        if text:
            sections[current_key] = text

    for line in lines:
        match = _ITEM_HEADER_RE.match(line) if len(line) <= _MAX_HEADER_LINE_LEN else None
        if match:
            flush()
            item_number = match.group(1).lower()
            current_key = f"item_{item_number}"
            buffer = [line]
        else:
            buffer.append(line)
    flush()

    if len(sections) <= 1:
        # No Item structure detected at all — fall back to whole-document text
        # under a generic key rather than returning a near-empty sections map.
        full_text = _normalize_whitespace(soup.get_text(separator="\n"))
        return {"_full_text": full_text} if full_text else {}

    return sections


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
