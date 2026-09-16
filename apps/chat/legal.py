from datetime import date


CURRENT_TERMS_VERSION = '0.1'
CURRENT_PRIVACY_VERSION = '0.1'
CURRENT_CHILD_DECLARATION_VERSION = '0.1'


def is_adult(birth_date: date, today: date | None = None) -> bool:
    reference_date = today or date.today()
    age = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age >= 18


def current_legal_versions():
    return {
        'terms_version': CURRENT_TERMS_VERSION,
        'privacy_version': CURRENT_PRIVACY_VERSION,
    }
