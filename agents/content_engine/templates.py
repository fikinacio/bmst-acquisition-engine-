"""
Content validators for LinkedIn and Instagram post drafts.

FORBIDDEN_PHRASES
    Clichéd phrases banned from all generated content (PRD Section 12.17).

validate_linkedin_post(text) -> tuple[bool, list[str]]
    Rules:
      * 150–250 words
      * No phrase from FORBIDDEN_PHRASES (Unicode-normalised, case-insensitive)
      * No proper-noun sequences of 3+ consecutive capitalised words (company name guard)

validate_instagram_post(text) -> tuple[bool, list[str]]
    Rules:
      * Fewer than 100 words
      * Last token (punctuation stripped) equals "audit.biscaplus.com"
"""

import re
import unicodedata

FORBIDDEN_PHRASES: list[str] = [
    "no mundo actual",
    "cada vez mais competitivo",
    "num contexto de",
    "e fundamental",       # normalised form of "é fundamental"
    "nas empresas modernas",
]

# Prepositions / articles that don't count toward a proper-noun run
_STOPWORDS: frozenset[str] = frozenset({
    "de", "da", "do", "dos", "das", "em", "no", "na", "nos", "nas",
    "a", "o", "as", "os", "e", "para", "por", "com", "sem", "ao", "aos",
    "the", "of", "in", "and", "for", "to", "at",
})


def _normalise(text: str) -> str:
    """Lowercase + strip diacritics for locale-safe comparison."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _count_words(text: str) -> int:
    return len(text.split())


def _contains_forbidden(text: str) -> list[str]:
    """Return any forbidden phrases found (uses normalised comparison)."""
    norm = _normalise(text)
    return [p for p in FORBIDDEN_PHRASES if _normalise(p) in norm]


def _has_long_proper_noun_run(text: str) -> bool:
    """
    Return True when 3+ consecutive capitalised words appear (company-name heuristic).

    Stopwords are skipped — they neither extend nor break a run.
    ALL-CAPS acronyms of 2 chars are also skipped (they are typically abbreviations
    for sectors or countries, not company identifiers).
    """
    tokens = re.findall(r"\b\w+\b", text)
    run = 0
    for token in tokens:
        if token.lower() in _STOPWORDS:
            continue
        # skip very short ALL-CAPS tokens (e.g. "AI", "HR", "TI", "PT")
        if len(token) <= 2 and token.isupper():
            run = 0
            continue
        if len(token) >= 3 and token[0].isupper():
            run += 1
            if run >= 3:
                return True
        else:
            run = 0
    return False


# ── Validators ────────────────────────────────────────────────────────────────

def validate_linkedin_post(text: str) -> tuple[bool, list[str]]:
    """
    Validate a LinkedIn post draft.

    Returns (is_valid, list_of_violation_strings).
    An empty violation list means the post passes all checks.
    """
    violations: list[str] = []

    word_count = _count_words(text)
    if word_count < 150:
        violations.append(
            f"Too short: {word_count} words — minimum is 150."
        )
    elif word_count > 250:
        violations.append(
            f"Too long: {word_count} words — maximum is 250."
        )

    for phrase in _contains_forbidden(text):
        violations.append(f'Contains forbidden phrase: "{phrase}"')

    if _has_long_proper_noun_run(text):
        violations.append(
            "Contains a sequence of 3+ consecutive capitalised words — "
            "possible company name. All client references must be removed."
        )

    return (len(violations) == 0, violations)


def validate_instagram_post(text: str) -> tuple[bool, list[str]]:
    """
    Validate an Instagram post draft.

    Returns (is_valid, list_of_violation_strings).
    """
    violations: list[str] = []

    word_count = _count_words(text)
    if word_count >= 100:
        violations.append(
            f"Too long: {word_count} words — must be fewer than 100."
        )

    words = text.strip().split()
    last_token = re.sub(r"[.,!?;:]+$", "", words[-1]) if words else ""
    if last_token != "audit.biscaplus.com":
        violations.append(
            f'Post must end with "audit.biscaplus.com" — '
            f'found "{last_token}" instead.'
        )

    return (len(violations) == 0, violations)
