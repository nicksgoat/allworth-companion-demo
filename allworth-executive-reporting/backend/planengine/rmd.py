"""SECURE 2.0 RMD calculation using the Uniform Lifetime Table."""

from decimal import Decimal


UNIFORM_LIFETIME = {
    72: Decimal("27.4"), 73: Decimal("26.5"), 74: Decimal("25.5"),
    75: Decimal("24.6"), 76: Decimal("23.7"), 77: Decimal("22.9"),
    78: Decimal("22.0"), 79: Decimal("21.1"), 80: Decimal("20.2"),
    81: Decimal("19.4"), 82: Decimal("18.5"), 83: Decimal("17.7"),
    84: Decimal("16.8"), 85: Decimal("16.0"), 86: Decimal("15.2"),
    87: Decimal("14.4"), 88: Decimal("13.7"), 89: Decimal("12.9"),
    90: Decimal("12.2"), 91: Decimal("11.5"), 92: Decimal("10.8"),
    93: Decimal("10.1"), 94: Decimal("9.5"), 95: Decimal("8.9"),
    96: Decimal("8.4"), 97: Decimal("7.8"), 98: Decimal("7.3"),
    99: Decimal("6.8"), 100: Decimal("6.4"), 101: Decimal("6.0"),
    102: Decimal("5.6"), 103: Decimal("5.2"), 104: Decimal("4.9"),
    105: Decimal("4.6"), 106: Decimal("4.3"), 107: Decimal("4.1"),
    108: Decimal("3.9"), 109: Decimal("3.7"), 110: Decimal("3.5"),
    111: Decimal("3.4"), 112: Decimal("3.3"), 113: Decimal("3.1"),
    114: Decimal("3.0"), 115: Decimal("2.9"), 116: Decimal("2.8"),
    117: Decimal("2.7"), 118: Decimal("2.5"), 119: Decimal("2.3"),
    120: Decimal("2.0"),
}


def rmd_start_age(birth_year: int) -> int:
    if birth_year >= 1960:
        return 75
    if birth_year >= 1951:
        return 73
    return 72


def rmd_for(balance: Decimal, age: int, birth_year: int, **_: object) -> Decimal:
    if age < rmd_start_age(birth_year) or balance <= 0:
        return Decimal("0")
    factor = UNIFORM_LIFETIME.get(min(age, 120), Decimal("2.0"))
    return Decimal(balance) / factor
