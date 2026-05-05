from dataclasses import dataclass
from underwriting import UnderwritingResult


@dataclass
class Verdict:
    label: str
    color: str
    reasons: list[str]
    warnings: list[str]


def evaluate(result: UnderwritingResult) -> Verdict:
    reasons = []
    warnings = []
    score = 0

    if result.cash_on_cash_return >= 8:
        score += 2
        reasons.append(f"Strong cash-on-cash return ({result.cash_on_cash_return:.1f}%)")
    elif result.cash_on_cash_return >= 5:
        score += 1
        reasons.append(f"Acceptable cash-on-cash return ({result.cash_on_cash_return:.1f}%)")
    else:
        score -= 1
        warnings.append(f"Weak cash-on-cash return ({result.cash_on_cash_return:.1f}% — target 8%+)")

    if result.cap_rate >= 7:
        score += 2
        reasons.append(f"Strong cap rate ({result.cap_rate:.1f}%)")
    elif result.cap_rate >= 5:
        score += 1
        reasons.append(f"Acceptable cap rate ({result.cap_rate:.1f}%)")
    else:
        score -= 1
        warnings.append(f"Low cap rate ({result.cap_rate:.1f}% — target 5%+)")

    if result.monthly_cash_flow > 300:
        score += 2
        reasons.append(f"Positive monthly cash flow (${result.monthly_cash_flow:,.0f}/mo)")
    elif result.monthly_cash_flow > 0:
        score += 1
        reasons.append(f"Slightly positive cash flow (${result.monthly_cash_flow:,.0f}/mo)")
    else:
        score -= 2
        warnings.append(f"Negative monthly cash flow (${result.monthly_cash_flow:,.0f}/mo)")

    if result.dscr >= 1.25:
        score += 1
        reasons.append(f"DSCR healthy ({result.dscr:.2f})")
    elif result.dscr >= 1.0:
        reasons.append(f"DSCR acceptable ({result.dscr:.2f})")
    else:
        score -= 2
        warnings.append(f"DSCR below 1.0 ({result.dscr:.2f}) — lender risk")

    if result.gross_rent_multiplier <= 10:
        score += 1
        reasons.append(f"Good price-to-rent ratio (GRM {result.gross_rent_multiplier:.1f})")
    elif result.gross_rent_multiplier <= 15:
        reasons.append(f"Moderate price-to-rent ratio (GRM {result.gross_rent_multiplier:.1f})")
    else:
        score -= 1
        warnings.append(f"High price-to-rent ratio (GRM {result.gross_rent_multiplier:.1f})")

    if score >= 6:
        label, color = "BUY", "green"
    elif score >= 2:
        label, color = "MAYBE", "orange"
    else:
        label, color = "PASS", "red"

    return Verdict(label=label, color=color, reasons=reasons, warnings=warnings)
