import re

TOKEN_RE = re.compile(r"(?u)\b[\w][\w.+#/-]*\b")
LOCATOR_PATTERNS = (
    re.compile(
        r"^\s*(?P<target>.+?)\s+(?:is|are)\s+in\s+(?:which|what)\s+"
        r"(?P<kind>section|subsection|chapter|page)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:in\s+)?(?:which|what)\s+(?P<kind>section|subsection|chapter|page)\s+"
        r"(?:is|are)\s+(?P<target>.+?)(?:\s+in)?\s*[?.!]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:which|what)\s+(?P<kind>section|subsection|chapter|page)\s+"
        r"(?:contains|covers|describes)\s+(?P<target>.+?)\s*[?.!]*$",
        re.IGNORECASE,
    ),
)
NUMBERED_HEADING_RE = re.compile(
    r"(?<![\d.])(?P<number>\d+(?:\.\d+)*)\s+(?P<title>[^\r\n]{1,300})"
)


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def estimate_tokens(text: str) -> int:
    # A conservative model-independent estimate that handles prose and code.
    return max(1, (len(text) + 3) // 4)


def normalize_question(text: str) -> str:
    return " ".join(tokenize(text))


def compact_alphanumeric(text: str) -> str:
    """Normalize spacing lost during PDF extraction without changing stored source text."""
    return "".join(character.casefold() for character in text if character.isalnum())


def find_compact_span(text: str, needle: str) -> tuple[int, int] | None:
    """Find text while ignoring whitespace and punctuation, retaining original offsets."""
    compact_needle = compact_alphanumeric(needle)
    if not compact_needle:
        return None
    compact_chars: list[str] = []
    original_offsets: list[int] = []
    for offset, character in enumerate(text):
        if character.isalnum():
            compact_chars.append(character.casefold())
            original_offsets.append(offset)
    compact_text = "".join(compact_chars)
    start = compact_text.find(compact_needle)
    if start < 0:
        return None
    end = start + len(compact_needle) - 1
    return original_offsets[start], original_offsets[end] + 1


def humanize_compound_label(text: str) -> str:
    """Make common PDF-glued labels such as PDNtype readable without a dictionary."""
    value = " ".join(text.split()).strip(" ,:;.-")
    value = re.sub(r"([A-Z]{2,})([a-z]{2,})", r"\1 \2", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return " ".join(value.split())


def parse_locator_query(text: str) -> tuple[str, str] | None:
    """Return the requested location kind and subject for section/chapter/page questions."""
    for pattern in LOCATOR_PATTERNS:
        match = pattern.search(text)
        if match:
            target = match.group("target").strip(" \t\r\n'\"?.!")
            if target:
                return match.group("kind").casefold(), target
    return None


def find_numbered_heading(text: str, target: str) -> tuple[str, str] | None:
    """Find a numbered heading even when a PDF converter flattened its preceding newline."""
    compact_target = compact_alphanumeric(target)
    if not compact_target:
        return None
    for match in NUMBERED_HEADING_RE.finditer(text):
        title = match.group("title")
        if compact_target in compact_alphanumeric(title):
            return match.group("number"), title
    return None
