from decimal import Decimal, InvalidOperation


def assess(app):
    reasons = []
    score = 0
    fields = app.get('fields', {})
    errors = [i for i in app.get('issues', []) if i.get('severity') == 'error']
    conflicts = [i for i in errors if str(i.get('code', '')).startswith('conflict_')]
    if conflicts:
        score += min(35, len(conflicts) * 12)
        reasons.append('Conflicting values were found across uploaded documents.')
    if not app.get('documents'):
        score += 35
        reasons.append('No source documents are available.')
    names = {str(s.get('value', '')).strip().casefold() for s in fields.get('full_name', {}).get('sources', []) if s.get('value')}
    if len(names) > 1:
        score += 25
        reasons.append('Patient names do not match across documents.')
    try:
        amount = Decimal(str(fields.get('bill_total', {}).get('value', '')).replace(',', ''))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        if fields.get('bill_total', {}).get('value'):
            score += 20
            reasons.append('The claimed amount could not be validated as a positive amount.')
    if any('duplicate' in str(i.get('code', '')).casefold() for i in app.get('issues', [])):
        score += 20
        reasons.append('Duplicate evidence requires review.')
    level = 'low' if score < 25 else 'medium' if score < 55 else 'high'
    return {'status': 'review_required' if score else 'no_indicators', 'level': level, 'score': min(score, 100),
            'explanation': 'This is a document consistency check, not a fraud verdict.', 'reasons': reasons or ['No immediate document consistency indicators were found.']}
