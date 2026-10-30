from datetime import date
import re


def parse_document_date(value: str) -> date | None:
    """Parse common policy/hospital date formats without changing the stored evidence."""
    text = str(value or '').strip()
    if not text:
        return None
    for candidate in (text, text.replace('/', '-').replace('.', '-')):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    match = re.fullmatch(r'(\d{1,2})-(\d{1,2})-(\d{4})', text.replace('/', '-').replace('.', '-'))
    if not match:
        return None
    first, second, year = (int(part) for part in match.groups())
    # Indian policy and hospital documents usually use day-first notation.
    try:
        return date(year, second, first) if first > 12 else date(year, second, first)
    except ValueError:
        try:
            return date(year, first, second)
        except ValueError:
            return None
