import streamlit as st
from underwriting import PropertyInputs, calculate
from scenarios import build_scenarios
from verdicts import evaluate

st.set_page_config(page_title="Real Estate Deal Evaluator", layout="wide")

st.title("Real Estate Investment Evaluator")
st.caption("Enter property details to get underwriting analysis, scenario comparison, and a buy/maybe/pass verdict.")

with st.form("property_form"):
    st.subheader("Property Details")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Acquisition**")
        purchase_price = st.number_input("Purchase Price ($)", min_value=10_000, value=350_000, step=5_000)
        down_payment_pct = st.slider("Down Payment (%)", min_value=3, max_value=50, value=20)
        interest_rate = st.number_input("Interest Rate (%)", min_value=1.0, max_value=20.0, value=7.0, step=0.125, format="%.3f")
        loan_term_years = st.selectbox("Loan Term (years)", options=[15, 20, 25, 30], index=3)

    with col2:
        st.markdown("**Income & Expenses**")
        monthly_rent = st.number_input("Monthly Rent ($)", min_value=100, value=2_500, step=50)
        vacancy_rate_pct = st.slider("Vacancy Rate (%)", min_value=0, max_value=30, value=5)
        monthly_expenses = st.number_input(
            "Monthly Operating Expenses ($)",
            min_value=0,
            value=600,
            step=50,
            help="Property tax, insurance, maintenance, property management, HOA, etc.",
        )

    st.markdown("**Hold Strategy**")
    col3, col4 = st.columns(2)
    with col3:
        annual_appreciation_pct = st.number_input("Annual Appreciation (%)", min_value=0.0, max_value=20.0, value=3.0, step=0.5, format="%.1f")
    with col4:
        holding_years = st.number_input("Holding Period (years)", min_value=1, max_value=30, value=5, step=1)

    submitted = st.form_submit_button("Analyze Deal", use_container_width=True, type="primary")

if submitted:
    inputs = PropertyInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        interest_rate=interest_rate,
        loan_term_years=loan_term_years,
        monthly_rent=monthly_rent,
        vacancy_rate_pct=vacancy_rate_pct,
        monthly_expenses=monthly_expenses,
        annual_appreciation_pct=annual_appreciation_pct,
        holding_years=holding_years,
    )

    result = calculate(inputs)
    verdict = evaluate(result)

    st.divider()

    verdict_col, _ = st.columns([1, 2])
    with verdict_col:
        color_map = {"BUY": "🟢", "MAYBE": "🟡", "PASS": "🔴"}
        st.metric("Verdict", f"{color_map[verdict.label]}  {verdict.label}")

    if verdict.reasons:
        with st.expander("Strengths", expanded=True):
            for r in verdict.reasons:
                st.write(f"✓ {r}")

    if verdict.warnings:
        with st.expander("Concerns", expanded=True):
            for w in verdict.warnings:
                st.write(f"⚠ {w}")

    st.divider()
    st.subheader("Base Case Underwriting")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Monthly Cash Flow", f"${result.monthly_cash_flow:,.0f}")
    m2.metric("Cash-on-Cash Return", f"{result.cash_on_cash_return:.1f}%")
    m3.metric("Cap Rate", f"{result.cap_rate:.1f}%")
    m4.metric("DSCR", f"{result.dscr:.2f}")

    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Monthly Mortgage", f"${result.monthly_mortgage:,.0f}")
    m6.metric("Net Operating Income", f"${result.net_operating_income:,.0f}/yr")
    m7.metric("Gross Rent Multiplier", f"{result.gross_rent_multiplier:.1f}x")
    m8.metric("Cash Invested", f"${result.total_cash_invested:,.0f}")

    m9, m10, m11 = st.columns(3)
    m9.metric("Projected Value", f"${result.projected_value:,.0f}", f"+${result.projected_value - purchase_price:,.0f}")
    m10.metric("Total Profit", f"${result.total_profit:,.0f}")
    m11.metric("Annualized ROI", f"{result.annualized_roi:.1f}%")

    st.divider()
    st.subheader("Scenario Comparison")
    st.caption("Bear: higher rates, lower rent, higher expenses, lower appreciation. Bull: opposite.")

    scenarios = build_scenarios(inputs)

    import pandas as pd

    rows = []
    for s in scenarios:
        r = s.result
        rows.append({
            "Scenario": s.name,
            "Monthly Cash Flow": f"${r.monthly_cash_flow:,.0f}",
            "Cash-on-Cash (%)": f"{r.cash_on_cash_return:.1f}%",
            "Cap Rate (%)": f"{r.cap_rate:.1f}%",
            "DSCR": f"{r.dscr:.2f}",
            "Annual Cash Flow": f"${r.annual_cash_flow:,.0f}",
            "Projected Value": f"${r.projected_value:,.0f}",
            "Annualized ROI (%)": f"{r.annualized_roi:.1f}%",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df.set_index("Scenario"), use_container_width=True)
