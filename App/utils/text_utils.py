import re


def strip_punct(text: str) -> str:
    """Lower-case + remove all punctuation + collapse whitespace."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()
