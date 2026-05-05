from dataclasses import dataclass


@dataclass
class PropertyInputs:
    purchase_price: float
    down_payment_pct: float
    interest_rate: float
    loan_term_years: int
    monthly_rent: float
    vacancy_rate_pct: float
    monthly_expenses: float
    annual_appreciation_pct: float
    holding_years: int


@dataclass
class UnderwritingResult:
    loan_amount: float
    monthly_mortgage: float
    effective_gross_income: float
    net_operating_income: float
    monthly_cash_flow: float
    annual_cash_flow: float
    cash_on_cash_return: float
    cap_rate: float
    gross_rent_multiplier: float
    total_cash_invested: float
    projected_value: float
    total_profit: float
    annualized_roi: float
    dscr: float


def calculate(inputs: PropertyInputs) -> UnderwritingResult:
    down_payment = inputs.purchase_price * (inputs.down_payment_pct / 100)
    loan_amount = inputs.purchase_price - down_payment

    monthly_rate = (inputs.interest_rate / 100) / 12
    n = inputs.loan_term_years * 12
    if monthly_rate > 0:
        monthly_mortgage = loan_amount * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)
    else:
        monthly_mortgage = loan_amount / n

    vacancy_loss = inputs.monthly_rent * (inputs.vacancy_rate_pct / 100)
    effective_gross_income = inputs.monthly_rent - vacancy_loss
    net_operating_income = (effective_gross_income - inputs.monthly_expenses) * 12

    monthly_cash_flow = effective_gross_income - inputs.monthly_expenses - monthly_mortgage
    annual_cash_flow = monthly_cash_flow * 12

    total_cash_invested = down_payment
    cash_on_cash_return = (annual_cash_flow / total_cash_invested * 100) if total_cash_invested > 0 else 0

    cap_rate = (net_operating_income / inputs.purchase_price * 100) if inputs.purchase_price > 0 else 0
    gross_rent_multiplier = (inputs.purchase_price / (inputs.monthly_rent * 12)) if inputs.monthly_rent > 0 else 0

    projected_value = inputs.purchase_price * ((1 + inputs.annual_appreciation_pct / 100) ** inputs.holding_years)
    total_profit = (projected_value - inputs.purchase_price) + (annual_cash_flow * inputs.holding_years)
    annualized_roi = ((total_profit / total_cash_invested) / inputs.holding_years * 100) if total_cash_invested > 0 and inputs.holding_years > 0 else 0

    dscr = (net_operating_income / (monthly_mortgage * 12)) if monthly_mortgage > 0 else 0

    return UnderwritingResult(
        loan_amount=loan_amount,
        monthly_mortgage=monthly_mortgage,
        effective_gross_income=effective_gross_income,
        net_operating_income=net_operating_income,
        monthly_cash_flow=monthly_cash_flow,
        annual_cash_flow=annual_cash_flow,
        cash_on_cash_return=cash_on_cash_return,
        cap_rate=cap_rate,
        gross_rent_multiplier=gross_rent_multiplier,
        total_cash_invested=total_cash_invested,
        projected_value=projected_value,
        total_profit=total_profit,
        annualized_roi=annualized_roi,
        dscr=dscr,
    )
