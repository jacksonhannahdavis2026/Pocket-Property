import re

import pandas as pd
import streamlit as st

from underwriting import PropertyInputs, calculate
from scenarios import build_scenarios
from verdicts import evaluate


st.set_page_config(page_title="Property Pocket", layout="wide")

st.title("Property Pocket")
st.caption("Fast acquisition screen for STR / rental property underwriting.")


def dollars(value):
    return f"${value:,.0f}"


def dollars_month(value):
    return f"${value:,.0f}/mo"


def pct(value):
    return f"{value:.1%}"


def multiple(value):
    return f"{value:.2f}x"


def parse_listing_text(text):
    parsed = {}

    if not text:
        return parsed

    clean_text = text.replace(",", "")

    price_match = re.search(r"\$?\s?(\d{3,}[,\d]*)", text)
    if price_match:
        price = price_match.group(1).replace(",", "")
        parsed["ask_price"] = int(price)
        parsed["offer_price"] = int(price)

    bed_match = re.search(r"(\d+\.?\d*)\s*(bed|beds|bd|bds)\b", text, re.IGNORECASE)
    if bed_match:
        parsed["bedrooms"] = float(bed_match.group(1))

    bath_match = re.search(r"(\d+\.?\d*)\s*(bath|baths|ba)\b", text, re.IGNORECASE)
    if bath_match:
        parsed["bathrooms"] = float(bath_match.group(1))

    sqft_match = re.search(
        r"(\d{3,6})\s*(sqft|sq ft|square feet)", clean_text, re.IGNORECASE
    )
    if sqft_match:
        parsed["square_feet"] = int(sqft_match.group(1))

    hoa_match = re.search(r"(hoa|HOA).{0,30}\$?\s?(\d{2,5})", text, re.IGNORECASE)
    if not hoa_match:
        hoa_match = re.search(r"\$?\s?(\d{2,5}).{0,30}(hoa|HOA)", text, re.IGNORECASE)

    if hoa_match:
        nums = re.findall(r"\d{2,5}", hoa_match.group(0).replace(",", ""))
        if nums:
            parsed["hoa_monthly"] = int(nums[0])

    tax_match = re.search(
        r"(tax|taxes|property tax).{0,40}\$?\s?(\d{3,6})", text, re.IGNORECASE
    )
    if tax_match:
        nums = re.findall(r"\d{3,6}", tax_match.group(0).replace(",", ""))
        if nums:
            annual_tax_estimate = int(nums[0])
            parsed["taxes_insurance_monthly"] = round(annual_tax_estimate / 12)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if re.search(r"\b[A-Z]{2}\s+\d{5}\b", line):
            parsed["property_address"] = line

            city_match = re.search(r",\s*([^,]+),\s*[A-Z]{2}\s+\d{5}", line)
            if city_match:
                parsed["market_city"] = city_match.group(1).strip()

            break

    return parsed


default_values = {
    "property_address": "",
    "market_city": "",
    "bedrooms": 2.0,
    "bathrooms": 2.0,
    "square_feet": 1200,
    "ask_price": 450000,
    "offer_price": 430000,
    "prior_year_annual_income": 45000,
    "hoa_monthly": 1000,
    "taxes_insurance_monthly": 365,
    "utilities_monthly": 0,
    "target_dscr": 1.00,
    "down_payment_pct_input": 10.0,
    "interest_rate_input": 6.75,
    "loan_term_years": 30,
    "closing_costs": 0,
    "case_scenario": "Base",
    "county_appraisal_value": 430000,
    "land_allocation_pct_input": 20.0,
    "annual_w2_income": 354000,
    "five_year_asset_pct_input": 10.0,
    "seven_year_asset_pct_input": 3.0,
    "fifteen_year_asset_pct_input": 7.0,
    "twenty_seven_half_year_asset_pct_input": 80.0,
    "annual_market_appreciation_input": 1.5,
    "annual_rent_appreciation_input": 1.5,
    "cost_to_sell_pct_input": 3.0,
    "depreciation_recapture_tax_rate_input": 25.0,
}

for key, value in default_values.items():
    if key not in st.session_state:
        st.session_state[key] = value


listing_text = st.text_area(
    "Paste Zillow URL or listing text",
    placeholder="Paste Zillow URL or listing details here. For now, listing text works best.\n\nExample:\n$725,000\n2 bed\n2 bath\n1,204 sqft\n$675 monthly HOA\n732 Scenic Gulf Dr #D301, Miramar Beach, FL 32550",
    height=120,
)

if st.button("Load Property Analysis", use_container_width=True):
    parsed = parse_listing_text(listing_text)

    for key, value in parsed.items():
        st.session_state[key] = value

    if parsed:
        st.success("Property details loaded into the model.")
    else:
        st.warning(
            "No property details found yet. Try pasting more listing text instead of only the URL."
        )

st.divider()

with st.form("property_form"):
    st.subheader("Quick Deal Inputs")
    st.caption(
        "The key deal drivers. Ask price, HOA, and taxes can load from listing text; income usually needs Zillow, AirDNA, Rabbu, actuals, or owner data."
    )

    ask_price = st.number_input("Ask Price ($)", step=5000, key="ask_price")
    offer_price = st.number_input("Offer Price ($)", step=5000, key="offer_price")
    prior_year_annual_income = st.number_input(
        "Estimated / Prior Year Annual Income ($)",
        step=1000,
        key="prior_year_annual_income",
    )
    hoa_monthly = st.number_input("HOA ($/mo)", step=100, key="hoa_monthly")
    taxes_insurance_monthly = st.number_input(
        "Taxes / Insurance ($/mo)",
        step=25,
        key="taxes_insurance_monthly",
    )

    submitted = st.form_submit_button("Analyze Deal", use_container_width=True, type="primary")

    st.divider()

    with st.expander("Property Details", expanded=False):
        st.caption("Loads automatically from listing text where available.")
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            property_address = st.text_input("Property Address", key="property_address")
            market_city = st.text_input("Market / City", key="market_city")
            bedrooms = st.number_input("Bedrooms", step=0.5, key="bedrooms")
        with pcol2:
            bathrooms = st.number_input("Bathrooms", step=0.5, key="bathrooms")
            square_feet = st.number_input("Square Feet", step=50, key="square_feet")
            utilities_monthly = st.number_input(
                "Utilities (not in HOA, $/mo)",
                step=25,
                key="utilities_monthly",
            )

    with st.expander("Financing", expanded=False):
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            down_payment_pct_input = st.number_input(
                "Down Payment %", step=1.0, key="down_payment_pct_input"
            )
            interest_rate_input = st.number_input(
                "Interest Rate %", step=0.125, key="interest_rate_input"
            )
            loan_term_years = st.number_input(
                "Loan Term (years)", step=1, key="loan_term_years"
            )
        with fcol2:
            closing_costs = st.number_input(
                "Closing Costs ($)", step=1000, key="closing_costs"
            )
            target_dscr = st.number_input("Target DSCR", step=0.05, key="target_dscr")

    with st.expander("Tax Strategy", expanded=False):
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            county_appraisal_value = st.number_input(
                "County Appraisal Value ($)", step=5000, key="county_appraisal_value"
            )
            land_allocation_pct_input = st.number_input(
                "Land Allocation %", step=1.0, key="land_allocation_pct_input"
            )
            annual_w2_income = st.number_input(
                "Annual W-2 Income ($)", step=5000, key="annual_w2_income"
            )
        with tcol2:
            five_year_asset_pct_input = st.number_input(
                "5-Year Asset %", step=1.0, key="five_year_asset_pct_input"
            )
            seven_year_asset_pct_input = st.number_input(
                "7-Year Asset %", step=1.0, key="seven_year_asset_pct_input"
            )
            fifteen_year_asset_pct_input = st.number_input(
                "15-Year Asset %", step=1.0, key="fifteen_year_asset_pct_input"
            )
            twenty_seven_half_year_asset_pct_input = st.number_input(
                "27.5-Year Asset %",
                step=1.0,
                key="twenty_seven_half_year_asset_pct_input",
            )

    with st.expander("Exit Assumptions", expanded=False):
        xcol1, xcol2 = st.columns(2)
        with xcol1:
            case_scenario = st.selectbox(
                "Case Scenario",
                ["Aggressive", "Base", "Conservative"],
                index=["Aggressive", "Base", "Conservative"].index(
                    st.session_state["case_scenario"]
                ),
                key="case_scenario",
            )
            annual_market_appreciation_input = st.number_input(
                "Annual Market Appreciation %",
                step=0.25,
                key="annual_market_appreciation_input",
            )
            annual_rent_appreciation_input = st.number_input(
                "Annual Rent Appreciation %",
                step=0.25,
                key="annual_rent_appreciation_input",
            )
        with xcol2:
            cost_to_sell_pct_input = st.number_input(
                "Cost to Sell %", step=0.25, key="cost_to_sell_pct_input"
            )
            depreciation_recapture_tax_rate_input = st.number_input(
                "Depreciation Recapture Tax Rate %",
                step=1.0,
                key="depreciation_recapture_tax_rate_input",
            )

    with st.expander("Feature Scorecard / Roadmap", expanded=False):
        roadmap_data = [
            {
                "Feature": "Paste listing text and parse key fields",
                "Status": "In progress",
                "Priority": "High",
                "Notes": "Currently parses price, beds, baths, sqft, HOA, taxes if present, address, and city.",
            },
            {
                "Feature": "Dynamic property tax estimate by location",
                "Status": "Backlog",
                "Priority": "High",
                "Notes": "Needs a property tax database or county/state lookup table. User wants taxes to update dynamically based on location.",
            },
            {
                "Feature": "Zillow URL auto-import",
                "Status": "Backlog",
                "Priority": "Medium",
                "Notes": "May require scraping API because Zillow can block automated requests.",
            },
            {
                "Feature": "Saved deal database",
                "Status": "Backlog",
                "Priority": "High",
                "Notes": "Save properties, assumptions, verdicts, and notes for deal pipeline tracking.",
            },
            {
                "Feature": "Market-level defaults",
                "Status": "Backlog",
                "Priority": "Medium",
                "Notes": "Auto-fill appreciation, taxes, insurance, and rent growth by market.",
            },
        ]

        roadmap_df = pd.DataFrame(roadmap_data)
        st.dataframe(roadmap_df, use_container_width=True, hide_index=True)


if submitted:
    inputs = PropertyInputs(
        ask_price=ask_price,
        offer_price=offer_price,
        down_payment_pct=down_payment_pct_input / 100,
        interest_rate=interest_rate_input / 100,
        prior_year_annual_income=prior_year_annual_income,
        loan_term_years=int(loan_term_years),
        case_scenario=case_scenario,
        hoa_monthly=hoa_monthly,
        taxes_insurance_monthly=taxes_insurance_monthly,
        utilities_monthly=utilities_monthly,
        county_appraisal_value=county_appraisal_value,
        land_allocation_pct=land_allocation_pct_input / 100,
        five_year_asset_pct=five_year_asset_pct_input / 100,
        seven_year_asset_pct=seven_year_asset_pct_input / 100,
        fifteen_year_asset_pct=fifteen_year_asset_pct_input / 100,
        twenty_seven_half_year_asset_pct=twenty_seven_half_year_asset_pct_input / 100,
        annual_w2_income=annual_w2_income,
        closing_costs=closing_costs,
        annual_market_appreciation=annual_market_appreciation_input / 100,
        annual_rent_appreciation=annual_rent_appreciation_input / 100,
        cost_to_sell_pct=cost_to_sell_pct_input / 100,
        depreciation_recapture_tax_rate=depreciation_recapture_tax_rate_input / 100,
        target_dscr=target_dscr,
    )

    results = calculate(inputs)
    verdict = evaluate(results)

    st.divider()

    st.subheader("Verdict")

    verdict_label = verdict.get("verdict", "REVIEW")

    if verdict_label == "BUY":
        st.success(f"🟢 {verdict_label}")
    elif verdict_label == "REVIEW":
        st.warning(f"🟡 {verdict_label}")
    else:
        st.error(f"🔴 {verdict_label}")

    if verdict_label == "BUY":
        summary = (
            "This deal appears attractive on core property economics and tax-enhanced returns. "
            "It deserves deeper diligence."
        )
    elif verdict_label == "REVIEW":
        summary = (
            "This deal has some attractive qualities, but the economics are not clean enough yet. "
            "Tighten the assumptions before moving forward."
        )
    else:
        summary = (
            "This deal should not move forward as currently modeled. "
            "The property-level economics are too weak before relying on tax benefits."
        )

    st.info(summary)

    strengths = verdict.get("strengths", [])
    reasons = verdict.get("reasons", [])

    if strengths:
        with st.expander("Strengths", expanded=True):
            for strength in strengths:
                st.write(f"✅ {strength}")

    if reasons:
        with st.expander("Concerns / Notes", expanded=True):
            for reason in reasons:
                st.write(f"⚠️ {reason}")

    st.divider()

    st.subheader("Property Snapshot")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Bedrooms", f"{bedrooms:g}")
    p2.metric("Bathrooms", f"{bathrooms:g}")
    p3.metric("Square Feet", f"{square_feet:,.0f}")
    p4.metric(
        "Price / Sq Ft", dollars(offer_price / square_feet) if square_feet else "N/A"
    )

    if property_address:
        st.caption(f"Address: {property_address}")

    st.divider()

    st.subheader("Investor Snapshot")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Offer Price", dollars(results["current_market_value"]))
    k2.metric("Down Payment", dollars(results["down_payment"]))
    k3.metric("Mortgage Balance", dollars(results["mortgage_balance"]))
    k4.metric("Seller Credits", dollars(results["seller_credits"]))

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Avg Monthly Revenue", dollars_month(results["average_monthly_revenue"]))
    k6.metric("Monthly Net", dollars_month(results["monthly_net"]))
    k7.metric("DSCR", f"{results['dscr']:.2f}")
    k8.metric("Revenue Gap", dollars(results["revenue_gap_dollars"]))

    st.divider()

    st.subheader("Return Profile")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric(
        "5-Year IRR",
        pct(results["five_year_irr"])
        if results["five_year_irr"] is not None
        else "N/A",
    )
    r2.metric(
        "Core 5-Year IRR",
        pct(results["core_five_year_irr"])
        if results["core_five_year_irr"] is not None
        else "N/A",
    )
    r3.metric("Equity Multiple", multiple(results["equity_multiple"]))
    r4.metric("Cash-on-Cash", pct(results["coc"]))

    r5, r6, r7, r8 = st.columns(4)
    r5.metric("Sale Price", dollars(results["sale_price"]))
    r6.metric("Net Sale Proceeds", dollars(results["net_sale_proceeds"]))
    r7.metric("Year-5 Cash Out", dollars(results["year_5_cash_out"]))
    r8.metric("Total Profit", dollars(results["total_profit"]))

    st.divider()

    st.subheader("Tax Strategy")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Depreciable Basis", dollars(results["depreciable_basis"]))
    t2.metric("Year-1 Depreciation", dollars(results["year_1_depreciation"]))
    t3.metric("Year-1 Tax Shield", dollars(results["year_1_tax_shield"]))
    t4.metric("Year 2+ Tax Shield", dollars(results["year_2_plus_tax_shield"]))

    st.divider()

    st.subheader("Cash Flow by Buydown Year")

    cash_flow_table = pd.DataFrame(
        [
            [
                "Year 1",
                results["monthly_net_year_1"],
                results["monthly_net_year_1"] * 12,
            ],
            [
                "Year 2",
                results["monthly_net_year_2"],
                results["monthly_net_year_2"] * 12,
            ],
            [
                "Year 3",
                results["monthly_net_year_3"],
                results["monthly_net_year_3"] * 12,
            ],
            [
                "Year 4+",
                results["monthly_net_year_4_plus"],
                results["monthly_net_year_4_plus"] * 12,
            ],
        ],
        columns=["Period", "Monthly Net", "Annual Net"],
    )

    st.dataframe(
        cash_flow_table.style.format(
            {
                "Monthly Net": "${:,.0f}",
                "Annual Net": "${:,.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Scenario Comparison")

    scenarios = build_scenarios(inputs)
    scenario_rows = []

    for name, scenario_results in scenarios.items():
        scenario_rows.append(
            {
                "Scenario": name,
                "Monthly Net": scenario_results["monthly_net"],
                "DSCR": scenario_results["dscr"],
                "5-Year IRR": scenario_results["five_year_irr"],
                "Core 5-Year IRR": scenario_results["core_five_year_irr"],
                "Equity Multiple": scenario_results["equity_multiple"],
                "Revenue Gap": scenario_results["revenue_gap_dollars"],
                "Year-5 Cash Out": scenario_results["year_5_cash_out"],
            }
        )

    scenario_df = pd.DataFrame(scenario_rows)

    st.dataframe(
        scenario_df.style.format(
            {
                "Monthly Net": "${:,.0f}",
                "DSCR": "{:.2f}",
                "5-Year IRR": "{:.1%}",
                "Core 5-Year IRR": "{:.1%}",
                "Equity Multiple": "{:.2f}x",
                "Revenue Gap": "${:,.0f}",
                "Year-5 Cash Out": "${:,.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
