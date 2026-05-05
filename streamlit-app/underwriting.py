from dataclasses import dataclass


@dataclass
class PropertyInputs:
    # Loan details
    loan_start_year: int = 2026
    ask_price: float = 450000
    offer_price: float = 430000
    down_payment_pct: float = 0.10
    interest_rate: float = 0.0675
    prior_year_annual_income: float = 45000
    loan_term_years: int = 30
    case_scenario: str = "Aggressive"

    # Monthly expenses
    hoa_monthly: float = 1000
    taxes_insurance_monthly: float = 365
    utilities_monthly: float = 0

    # Tax strategy
    county_appraisal_value: float = 430000
    land_allocation_pct: float = 0.20
    five_year_asset_pct: float = 0.10
    seven_year_asset_pct: float = 0.03
    fifteen_year_asset_pct: float = 0.07
    twenty_seven_half_year_asset_pct: float = 0.80
    annual_w2_income: float = 354000

    # Investor overview
    closing_costs: float = 0
    annual_market_appreciation: float = 0.02
    annual_rent_appreciation: float = 0.02
    cost_to_sell_pct: float = 0.03
    depreciation_recapture_tax_rate: float = 0.25
    target_dscr: float = 1.00


def pmt(rate, nper, pv):
    if rate == 0:
        return pv / nper
    return rate * pv / (1 - (1 + rate) ** -nper)


def remaining_loan_balance(rate, nper, payment, pv, periods_paid):
    balance = pv
    for _ in range(periods_paid):
        interest = balance * rate
        principal = payment - interest
        balance -= principal
    return max(balance, 0)


def federal_tax_estimate(income):
    """
    Simple federal tax estimate using the bracket structure from the Excel model.
    This is intentionally simplified for MVP underwriting.
    """
    brackets = [
        (11000, 0.10),
        (44725, 0.12),
        (95375, 0.22),
        (182100, 0.24),
        (231250, 0.32),
        (578125, 0.35),
        (float("inf"), 0.37),
    ]

    tax = 0
    lower = 0

    for upper, rate in brackets:
        taxable_amount = max(0, min(income, upper) - lower)
        tax += taxable_amount * rate
        lower = upper

        if income <= upper:
            break

    return tax


def npv(rate, cash_flows):
    return sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cash_flows))


def irr(cash_flows):
    """
    Basic IRR solver without extra packages.
    Returns None if IRR cannot be solved cleanly.
    """
    low = -0.95
    high = 1.00

    try:
        for _ in range(100):
            mid = (low + high) / 2
            value = npv(mid, cash_flows)

            if abs(value) < 0.0001:
                return mid

            if value > 0:
                low = mid
            else:
                high = mid

        return mid
    except Exception:
        return None


def get_scenario_assumptions(case_scenario):
    scenarios = {
        "Aggressive": {
            "revenue_multiplier": 1.00,
            "str_cost_pct": 0.10,
            "maintenance_pct": 0.00,
        },
        "Base": {
            "revenue_multiplier": 0.85,
            "str_cost_pct": 0.15,
            "maintenance_pct": 0.05,
        },
        "Conservative": {
            "revenue_multiplier": 0.70,
            "str_cost_pct": 0.20,
            "maintenance_pct": 0.10,
        },
    }

    return scenarios.get(case_scenario, scenarios["Base"])


def calculate(inputs: PropertyInputs):
    s = get_scenario_assumptions(inputs.case_scenario)

    # Loan details
    current_market_value = inputs.offer_price
    down_payment = inputs.offer_price * inputs.down_payment_pct
    mortgage_balance = inputs.offer_price - down_payment
    seller_credits = inputs.offer_price * 0.06
    seller_credit_pct = seller_credits / inputs.offer_price if inputs.offer_price else 0

    monthly_rate = inputs.interest_rate / 12
    loan_months = inputs.loan_term_years * 12
    monthly_mortgage_payment = pmt(monthly_rate, loan_months, mortgage_balance)
    monthly_interest = mortgage_balance * monthly_rate

    # Revenue
    expected_revenue_target = inputs.prior_year_annual_income
    revenue_multiplier = s["revenue_multiplier"]
    forecasted_annual_revenue = expected_revenue_target * revenue_multiplier
    average_monthly_revenue = forecasted_annual_revenue / 12

    # Expenses
    str_cost_pct = s["str_cost_pct"]
    maintenance_pct = s["maintenance_pct"]

    monthly_str_cost = average_monthly_revenue * str_cost_pct
    monthly_maintenance = average_monthly_revenue * maintenance_pct

    monthly_expenses = (
        monthly_mortgage_payment
        + inputs.hoa_monthly
        + inputs.taxes_insurance_monthly
        + inputs.utilities_monthly
        + monthly_str_cost
        + monthly_maintenance
    )

    annual_expenses = monthly_expenses * 12
    monthly_net = average_monthly_revenue - monthly_expenses

    # Buydown schedule from workbook
    monthly_mortgage_year_1 = pmt(
        (inputs.interest_rate - 0.03) / 12, loan_months, mortgage_balance
    )
    monthly_mortgage_year_2 = pmt(
        (inputs.interest_rate - 0.02) / 12, loan_months, mortgage_balance
    )
    monthly_mortgage_year_3 = pmt(
        (inputs.interest_rate - 0.01) / 12, loan_months, mortgage_balance
    )
    monthly_mortgage_year_4_plus = monthly_mortgage_payment

    monthly_expenses_year_1 = (
        monthly_expenses - monthly_mortgage_payment + monthly_mortgage_year_1
    )
    monthly_expenses_year_2 = (
        monthly_expenses - monthly_mortgage_payment + monthly_mortgage_year_2
    )
    monthly_expenses_year_3 = (
        monthly_expenses - monthly_mortgage_payment + monthly_mortgage_year_3
    )
    monthly_expenses_year_4_plus = (
        monthly_expenses - monthly_mortgage_payment + monthly_mortgage_year_4_plus
    )

    monthly_net_year_1 = average_monthly_revenue - monthly_expenses_year_1
    monthly_net_year_2 = average_monthly_revenue - monthly_expenses_year_2
    monthly_net_year_3 = average_monthly_revenue - monthly_expenses_year_3
    monthly_net_year_4_plus = average_monthly_revenue - monthly_expenses_year_4_plus

    # Tax strategy
    building_allocation_pct = 1 - inputs.land_allocation_pct
    depreciable_basis = inputs.county_appraisal_value * building_allocation_pct

    five_year_asset_basis = depreciable_basis * inputs.five_year_asset_pct
    seven_year_asset_basis = depreciable_basis * inputs.seven_year_asset_pct
    fifteen_year_asset_basis = depreciable_basis * inputs.fifteen_year_asset_pct
    twenty_seven_half_year_asset_basis = (
        depreciable_basis * inputs.twenty_seven_half_year_asset_pct
    )

    bonus_depreciation_year_1 = (
        five_year_asset_basis + seven_year_asset_basis + fifteen_year_asset_basis
    )

    annual_27_5_depreciation = twenty_seven_half_year_asset_basis / 27.5
    year_1_depreciation = bonus_depreciation_year_1 + annual_27_5_depreciation
    year_2_plus_depreciation = annual_27_5_depreciation

    taxes_before_depreciation_year_1 = federal_tax_estimate(inputs.annual_w2_income)
    income_after_depreciation_year_1 = inputs.annual_w2_income - year_1_depreciation
    taxes_after_depreciation_year_1 = federal_tax_estimate(
        income_after_depreciation_year_1
    )
    year_1_tax_shield = (
        taxes_before_depreciation_year_1 - taxes_after_depreciation_year_1
    )

    annual_tax_shields_year_2_plus = (
        -monthly_interest * 12
        - inputs.hoa_monthly * 12
        - inputs.taxes_insurance_monthly * 12
        - inputs.utilities_monthly * 12
        - monthly_str_cost * 12
        - monthly_maintenance * 12
        - year_2_plus_depreciation
    )

    taxes_before_tax_shield_year_2_plus = federal_tax_estimate(inputs.annual_w2_income)
    income_after_tax_shields_year_2_plus = (
        inputs.annual_w2_income + annual_tax_shields_year_2_plus
    )
    taxes_after_tax_shields_year_2_plus = federal_tax_estimate(
        income_after_tax_shields_year_2_plus
    )
    year_2_plus_tax_shield = (
        taxes_before_tax_shield_year_2_plus - taxes_after_tax_shields_year_2_plus
    )

    # Annual cash flow
    year_0_cash_flow = -down_payment - inputs.closing_costs
    year_1_cash_flow = monthly_net_year_1 * 12
    year_2_cash_flow = monthly_net_year_2 * 12
    year_3_cash_flow = monthly_net_year_3 * 12
    year_4_cash_flow = monthly_net_year_4_plus * 12
    year_5_cash_flow = monthly_net_year_4_plus * 12

    year_1_after_tax_cash_flow = year_1_cash_flow + year_1_tax_shield
    year_2_after_tax_cash_flow = year_2_cash_flow + year_2_plus_tax_shield
    year_3_after_tax_cash_flow = year_3_cash_flow + year_2_plus_tax_shield
    year_4_after_tax_cash_flow = year_4_cash_flow + year_2_plus_tax_shield
    year_5_after_tax_cash_flow = year_5_cash_flow + year_2_plus_tax_shield

    five_year_after_tax_income = (
        year_1_after_tax_cash_flow
        + year_2_after_tax_cash_flow
        + year_3_after_tax_cash_flow
        + year_4_after_tax_cash_flow
        + year_5_after_tax_cash_flow
    )

    # Investor overview / sale
    sale_price = inputs.offer_price * ((1 + inputs.annual_market_appreciation) ** 5)
    cost_to_sell = -sale_price * inputs.cost_to_sell_pct

    depreciation_recapture_tax = -inputs.depreciation_recapture_tax_rate * (
        year_1_depreciation + (year_2_plus_depreciation * 4)
    )

    loan_balance_at_sale = remaining_loan_balance(
        monthly_rate,
        loan_months,
        monthly_mortgage_payment,
        mortgage_balance,
        60,
    )

    net_sale_proceeds = (
        sale_price + cost_to_sell + depreciation_recapture_tax - loan_balance_at_sale
    )

    year_5_cash_out = net_sale_proceeds + five_year_after_tax_income

    # Core operating metrics
    annual_operating_expenses = 12 * (
        inputs.hoa_monthly
        + inputs.taxes_insurance_monthly
        + inputs.utilities_monthly
        + monthly_str_cost
        + monthly_maintenance
    )

    noi = forecasted_annual_revenue - annual_operating_expenses
    annual_debt_service = monthly_mortgage_payment * 12
    dscr = noi / annual_debt_service if annual_debt_service else 0

    breakeven_revenue = (
        inputs.target_dscr * annual_debt_service
    ) + annual_operating_expenses
    revenue_gap_dollars = breakeven_revenue - forecasted_annual_revenue
    revenue_gap_pct = (
        revenue_gap_dollars / forecasted_annual_revenue
        if forecasted_annual_revenue
        else 0
    )

    # Returns
    after_tax_cash_flows = [
        year_0_cash_flow,
        year_1_after_tax_cash_flow,
        year_2_after_tax_cash_flow,
        year_3_after_tax_cash_flow,
        year_4_after_tax_cash_flow,
        year_5_after_tax_cash_flow + net_sale_proceeds,
    ]

    core_cash_flows = [
        year_0_cash_flow,
        0,
        year_1_cash_flow,
        year_2_cash_flow,
        year_3_cash_flow,
        year_4_cash_flow + net_sale_proceeds,
    ]

    five_year_irr = irr(after_tax_cash_flows)
    core_five_year_irr = irr(core_cash_flows)

    equity_multiple = (
        (
            year_1_tax_shield
            + year_2_after_tax_cash_flow
            + year_3_after_tax_cash_flow
            + year_4_after_tax_cash_flow
            + year_5_after_tax_cash_flow
            + net_sale_proceeds
        )
        / abs(year_0_cash_flow)
        if year_0_cash_flow
        else 0
    )

    coc = (
        (
            (
                year_2_after_tax_cash_flow
                + year_3_after_tax_cash_flow
                + year_4_after_tax_cash_flow
                + year_5_after_tax_cash_flow
            )
            / 4
        )
        / abs(year_0_cash_flow)
        if year_0_cash_flow
        else 0
    )

    cap_rate = noi / inputs.offer_price if inputs.offer_price else 0

    return {
        # Main app compatibility
        "monthly_cash_flow": monthly_net,
        "cash_on_cash_return": coc,
        "cap_rate": cap_rate,
        "dscr": dscr,
        "monthly_mortgage": monthly_mortgage_payment,
        "noi": noi,
        "gross_rent_multiplier": inputs.offer_price / forecasted_annual_revenue
        if forecasted_annual_revenue
        else 0,
        "cash_invested": abs(year_0_cash_flow),
        "projected_value": sale_price,
        "total_profit": year_5_cash_out - abs(year_0_cash_flow),
        "annualized_roi": core_five_year_irr if core_five_year_irr is not None else 0,
        # Excel model outputs
        "current_market_value": current_market_value,
        "down_payment": down_payment,
        "mortgage_balance": mortgage_balance,
        "seller_credits": seller_credits,
        "seller_credit_pct": seller_credit_pct,
        "forecasted_annual_revenue": forecasted_annual_revenue,
        "average_monthly_revenue": average_monthly_revenue,
        "monthly_expenses": monthly_expenses,
        "annual_expenses": annual_expenses,
        "monthly_net": monthly_net,
        "monthly_net_year_1": monthly_net_year_1,
        "monthly_net_year_2": monthly_net_year_2,
        "monthly_net_year_3": monthly_net_year_3,
        "monthly_net_year_4_plus": monthly_net_year_4_plus,
        "depreciable_basis": depreciable_basis,
        "year_1_depreciation": year_1_depreciation,
        "year_2_plus_depreciation": year_2_plus_depreciation,
        "year_1_tax_shield": year_1_tax_shield,
        "year_2_plus_tax_shield": year_2_plus_tax_shield,
        "sale_price": sale_price,
        "cost_to_sell": cost_to_sell,
        "depreciation_recapture_tax": depreciation_recapture_tax,
        "net_sale_proceeds": net_sale_proceeds,
        "year_5_cash_out": year_5_cash_out,
        "annual_operating_expenses": annual_operating_expenses,
        "annual_debt_service": annual_debt_service,
        "breakeven_revenue": breakeven_revenue,
        "revenue_gap_dollars": revenue_gap_dollars,
        "revenue_gap_pct": revenue_gap_pct,
        "five_year_irr": five_year_irr,
        "core_five_year_irr": core_five_year_irr,
        "equity_multiple": equity_multiple,
        "coc": coc,
    }
