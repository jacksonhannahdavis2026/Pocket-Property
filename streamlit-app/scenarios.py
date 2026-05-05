from dataclasses import dataclass
from underwriting import PropertyInputs, UnderwritingResult, calculate


@dataclass
class Scenario:
    name: str
    inputs: PropertyInputs
    result: UnderwritingResult


def build_scenarios(base: PropertyInputs) -> list[Scenario]:
    bear = PropertyInputs(
        purchase_price=base.purchase_price,
        down_payment_pct=base.down_payment_pct,
        interest_rate=base.interest_rate + 1.0,
        loan_term_years=base.loan_term_years,
        monthly_rent=base.monthly_rent * 0.90,
        vacancy_rate_pct=min(base.vacancy_rate_pct + 5, 30),
        monthly_expenses=base.monthly_expenses * 1.20,
        annual_appreciation_pct=max(base.annual_appreciation_pct - 1.5, 0),
        holding_years=base.holding_years,
    )

    bull = PropertyInputs(
        purchase_price=base.purchase_price,
        down_payment_pct=base.down_payment_pct,
        interest_rate=max(base.interest_rate - 0.5, 1.0),
        loan_term_years=base.loan_term_years,
        monthly_rent=base.monthly_rent * 1.10,
        vacancy_rate_pct=max(base.vacancy_rate_pct - 2, 0),
        monthly_expenses=base.monthly_expenses * 0.90,
        annual_appreciation_pct=base.annual_appreciation_pct + 1.5,
        holding_years=base.holding_years,
    )

    return [
        Scenario("Bear", bear, calculate(bear)),
        Scenario("Base", base, calculate(base)),
        Scenario("Bull", bull, calculate(bull)),
    ]
