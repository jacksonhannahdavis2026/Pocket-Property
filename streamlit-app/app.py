import csv
import os
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from underwriting import PropertyInputs, calculate
from scenarios import build_scenarios
from verdicts import evaluate

SAVED_DEALS_PATH = os.path.join(os.path.dirname(__file__), "saved_deals.csv")

SAVED_DEALS_COLUMNS = [
    "saved_at",
    "deal_status",
    "property_address",
    "listing_url",
    "market_city",
    "ask_price",
    "offer_price",
    "prior_year_annual_income",
    "hoa_monthly",
    "taxes_insurance_monthly",
    "bedrooms",
    "bathrooms",
    "square_feet",
    "verdict",
    "monthly_net",
    "dscr",
    "core_five_year_irr",
    "five_year_irr",
    "revenue_gap_dollars",
    "revenue_gap_pct",
    "equity_multiple",
    "deal_notes",
    "updated_at",
]


def save_deal_to_csv(row: dict) -> None:
    new_row = {col: row.get(col, "") for col in SAVED_DEALS_COLUMNS}
    existing = load_saved_deals(reverse=False)
    if existing is None:
        combined = pd.DataFrame([new_row], columns=SAVED_DEALS_COLUMNS)
    else:
        for col in SAVED_DEALS_COLUMNS:
            if col not in existing.columns:
                existing[col] = ""
        combined = pd.concat(
            [existing[SAVED_DEALS_COLUMNS], pd.DataFrame([new_row], columns=SAVED_DEALS_COLUMNS)],
            ignore_index=True,
        )
    combined.to_csv(SAVED_DEALS_PATH, index=False)


def update_deal_in_csv(saved_at_key: str, updated_row: dict) -> bool:
    existing = load_saved_deals(reverse=False)
    if existing is None or existing == "malformed":
        return False
    mask = existing["saved_at"] == saved_at_key
    if not mask.any():
        return False
    for col, val in updated_row.items():
        if col in existing.columns:
            existing.loc[mask, col] = val
    existing.loc[mask, "updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    existing.to_csv(SAVED_DEALS_PATH, index=False)
    return True


def load_saved_deals(reverse: bool = True) -> pd.DataFrame | None:
    if not os.path.isfile(SAVED_DEALS_PATH):
        return None
    try:
        df = pd.read_csv(SAVED_DEALS_PATH, on_bad_lines="skip")
    except Exception:
        return "malformed"
    if df.empty:
        return None
    for col in SAVED_DEALS_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[SAVED_DEALS_COLUMNS]
    if reverse:
        df = df.iloc[::-1].reset_index(drop=True)
    return df


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

    url_match = re.search(r"https?://\S+", text)
    if url_match:
        parsed["listing_url"] = url_match.group(0).rstrip(")")

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
    "listing_url": "",
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

listing_url = st.text_input(
    "Listing URL",
    placeholder="https://www.zillow.com/homedetails/...",
    key="listing_url",
)

col_load, col_new = st.columns(2)

with col_load:
    if st.button("Load Property Analysis", use_container_width=True, type="primary"):
        parsed = parse_listing_text(listing_text)

        for key, value in parsed.items():
            st.session_state[key] = value

        if parsed:
            st.success("Property details loaded into the model.")
        else:
            st.warning(
                "No property details found yet. Try pasting more listing text instead of only the URL."
            )

with col_new:
    if st.button("Start New Deal", use_container_width=True):
        _property_reset = {
            "property_address": "",
            "listing_url": "",
            "market_city": "",
            "ask_price": 450000,
            "offer_price": 430000,
            "bedrooms": 2.0,
            "bathrooms": 2.0,
            "square_feet": 1200,
            "prior_year_annual_income": 45000,
            "hoa_monthly": 1000,
            "taxes_insurance_monthly": 365,
            "utilities_monthly": 0,
        }
        for key, value in _property_reset.items():
            st.session_state[key] = value
        st.session_state.pop("last_analyzed_deal", None)
        st.session_state.pop("loaded_saved_at", None)
        st.rerun()

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

    submitted = st.form_submit_button("Analyze Deal", use_container_width=True, type="primary")


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
    scenarios = build_scenarios(inputs)

    st.session_state["last_analyzed_deal"] = {
        "results": results,
        "verdict": verdict,
        "scenarios": scenarios,
        "ask_price": ask_price,
        "offer_price": offer_price,
        "prior_year_annual_income": prior_year_annual_income,
        "hoa_monthly": hoa_monthly,
        "taxes_insurance_monthly": taxes_insurance_monthly,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "square_feet": square_feet,
        "property_address": property_address,
        "listing_url": st.session_state.get("listing_url", ""),
        "market_city": market_city,
    }


_deal = st.session_state.get("last_analyzed_deal")

if _deal:
    results = _deal["results"]
    verdict = _deal["verdict"]
    scenarios = _deal["scenarios"]
    _ask_price = _deal["ask_price"]
    _offer_price = _deal["offer_price"]
    _prior_year_annual_income = _deal["prior_year_annual_income"]
    _hoa_monthly = _deal["hoa_monthly"]
    _taxes_insurance_monthly = _deal["taxes_insurance_monthly"]
    _bedrooms = _deal["bedrooms"]
    _bathrooms = _deal["bathrooms"]
    _square_feet = _deal["square_feet"]
    _property_address = _deal["property_address"]
    _listing_url = _deal.get("listing_url", "")
    _market_city = _deal["market_city"]

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

    st.subheader("Deal Snapshot")

    ds1, ds2 = st.columns(2)
    ds1.metric("Monthly Net", dollars_month(results["monthly_net"]))
    ds2.metric("DSCR", f"{results['dscr']:.2f}")

    ds3, ds4 = st.columns(2)
    ds3.metric(
        "Core 5-Year IRR",
        pct(results["core_five_year_irr"]) if results["core_five_year_irr"] is not None else "N/A",
    )
    ds4.metric("Revenue Gap", dollars(results["revenue_gap_dollars"]))

    ds5, _ = st.columns(2)
    ds5.metric(
        "Tax-Enhanced IRR",
        pct(results["five_year_irr"]) if results["five_year_irr"] is not None else "N/A",
    )

    with st.expander("What Would Make This Deal Work?", expanded=False):
        _breakeven = results.get("breakeven_revenue", 0)
        _current_rev = results.get("average_monthly_revenue", 0) * 12
        _gap_dollars = results["revenue_gap_dollars"]
        _gap_pct = results.get("revenue_gap_pct", 0)

        bm1, bm2 = st.columns(2)
        bm1.metric("Required Annual Revenue", dollars(_breakeven))
        bm2.metric("Current Annual Revenue", dollars(_current_rev))

        bm3, bm4 = st.columns(2)
        bm3.metric("Revenue Increase Needed", dollars(max(_gap_dollars, 0)))
        bm4.metric("Revenue Gap %", f"{_gap_pct:.1%}" if _gap_pct is not None else "N/A")

        if _gap_dollars <= 0:
            st.success("Revenue already clears the target DSCR.")
        elif _gap_pct <= 0.10:
            st.info("Small gap. This may be fixable with modestly better revenue or expenses.")
        elif _gap_pct <= 0.25:
            st.warning("Medium gap. The deal likely needs a lower offer price or stronger revenue proof.")
        else:
            st.error("Large gap. Move on unless revenue assumptions materially improve.")

        st.divider()
        st.markdown("**Investor Targets**")

        _tc1, _tc2 = st.columns(2)
        with _tc1:
            _tgt_dscr = st.number_input("Target DSCR", value=1.00, step=0.05, key="solver_tgt_dscr")
            _tgt_monthly_net = st.number_input("Min Monthly Net ($)", value=0, step=100, key="solver_tgt_monthly_net")
            _tgt_core_irr = st.number_input("Min Core 5-Yr IRR %", value=8.0, step=0.5, key="solver_tgt_core_irr")
            _tgt_coc = st.number_input("Min Cash-on-Cash %", value=4.0, step=0.5, key="solver_tgt_coc")
            _tgt_em = st.number_input("Min Equity Multiple", value=1.25, step=0.05, key="solver_tgt_em")
        with _tc2:
            _enforce_dscr = st.checkbox("Enforce DSCR", value=True, key="solver_enforce_dscr")
            _enforce_monthly_net = st.checkbox("Enforce Monthly Net", value=True, key="solver_enforce_monthly_net")
            _enforce_core_irr = st.checkbox("Enforce Core 5-Yr IRR", value=True, key="solver_enforce_core_irr")
            _enforce_coc = st.checkbox("Enforce Cash-on-Cash", value=False, key="solver_enforce_coc")
            _enforce_em = st.checkbox("Enforce Equity Multiple", value=False, key="solver_enforce_em")

        st.markdown("**Solver Levers**")
        _levers = st.multiselect(
            "Which levers can the solver adjust?",
            options=["Lower Offer Price", "Increase Annual Revenue", "Reduce HOA", "Reduce Taxes / Insurance"],
            default=["Lower Offer Price", "Increase Annual Revenue"],
            key="solver_levers",
        )

        if st.button("Run Deal Solver", use_container_width=True, type="primary", key="run_solver_btn"):
            _ss = st.session_state

            _base_kwargs = dict(
                ask_price=_ask_price,
                offer_price=_offer_price,
                down_payment_pct=_ss.get("down_payment_pct_input", 10) / 100,
                interest_rate=_ss.get("interest_rate_input", 6.75) / 100,
                prior_year_annual_income=_prior_year_annual_income,
                loan_term_years=int(_ss.get("loan_term_years", 30)),
                case_scenario=_ss.get("case_scenario", "Aggressive"),
                hoa_monthly=_hoa_monthly,
                taxes_insurance_monthly=_taxes_insurance_monthly,
                utilities_monthly=_ss.get("utilities_monthly", 0),
                county_appraisal_value=_ss.get("county_appraisal_value", _offer_price),
                land_allocation_pct=_ss.get("land_allocation_pct_input", 20) / 100,
                five_year_asset_pct=_ss.get("five_year_asset_pct_input", 10) / 100,
                seven_year_asset_pct=_ss.get("seven_year_asset_pct_input", 3) / 100,
                fifteen_year_asset_pct=_ss.get("fifteen_year_asset_pct_input", 7) / 100,
                twenty_seven_half_year_asset_pct=_ss.get("twenty_seven_half_year_asset_pct_input", 80) / 100,
                annual_w2_income=_ss.get("annual_w2_income", 354000),
                closing_costs=_ss.get("closing_costs", 0),
                annual_market_appreciation=_ss.get("annual_market_appreciation_input", 2) / 100,
                annual_rent_appreciation=_ss.get("annual_rent_appreciation_input", 2) / 100,
                cost_to_sell_pct=_ss.get("cost_to_sell_pct_input", 3) / 100,
                depreciation_recapture_tax_rate=_ss.get("depreciation_recapture_tax_rate_input", 25) / 100,
                target_dscr=_ss.get("target_dscr", 1.00),
            )

            if "Lower Offer Price" in _levers:
                _min_offer = int(_ask_price * 0.70)
                _offer_vals = list(range(int(_offer_price), _min_offer - 1, -5000))
                if not _offer_vals or _offer_vals[-1] > _min_offer:
                    _offer_vals.append(_min_offer)
            else:
                _offer_vals = [int(_offer_price)]

            if "Increase Annual Revenue" in _levers:
                _max_rev = int(_prior_year_annual_income * 1.50)
                _rev_vals = list(range(int(_prior_year_annual_income), _max_rev + 1, 2500))
                if not _rev_vals or _rev_vals[-1] < _max_rev:
                    _rev_vals.append(_max_rev)
            else:
                _rev_vals = [int(_prior_year_annual_income)]

            if "Reduce HOA" in _levers and _hoa_monthly > 0:
                _min_hoa = int(_hoa_monthly * 0.50)
                _hoa_vals = list(range(int(_hoa_monthly), _min_hoa - 1, -100))
                if not _hoa_vals or _hoa_vals[-1] > _min_hoa:
                    _hoa_vals.append(_min_hoa)
            else:
                _hoa_vals = [int(_hoa_monthly)]

            if "Reduce Taxes / Insurance" in _levers and _taxes_insurance_monthly > 0:
                _min_tax = int(_taxes_insurance_monthly * 0.60)
                _tax_vals = list(range(int(_taxes_insurance_monthly), _min_tax - 1, -50))
                if not _tax_vals or _tax_vals[-1] > _min_tax:
                    _tax_vals.append(_min_tax)
            else:
                _tax_vals = [int(_taxes_insurance_monthly)]

            def _meets_targets(r):
                if _enforce_dscr and r["dscr"] < _tgt_dscr:
                    return False
                if _enforce_monthly_net and r["monthly_net"] < _tgt_monthly_net:
                    return False
                if _enforce_core_irr and (r["core_five_year_irr"] is None or r["core_five_year_irr"] * 100 < _tgt_core_irr):
                    return False
                if _enforce_coc and (r.get("coc") is None or r["coc"] * 100 < _tgt_coc):
                    return False
                if _enforce_em and (r.get("equity_multiple") is None or r["equity_multiple"] < _tgt_em):
                    return False
                return True

            _found = []
            for _op in _offer_vals:
                for _rv in _rev_vals:
                    for _hoa in _hoa_vals:
                        for _tx in _tax_vals:
                            _r = calculate(PropertyInputs(**{**_base_kwargs,
                                "offer_price": _op,
                                "prior_year_annual_income": _rv,
                                "hoa_monthly": _hoa,
                                "taxes_insurance_monthly": _tx,
                            }))
                            if _meets_targets(_r):
                                _delta = (
                                    abs(_offer_price - _op)
                                    + abs(_rv - _prior_year_annual_income) * 10
                                    + abs(_hoa_monthly - _hoa) * 12
                                    + abs(_taxes_insurance_monthly - _tx) * 12
                                )
                                _found.append({
                                    "offer_price": _op,
                                    "prior_year_annual_income": _rv,
                                    "hoa_monthly": _hoa,
                                    "taxes_insurance_monthly": _tx,
                                    "monthly_net": _r["monthly_net"],
                                    "dscr": _r["dscr"],
                                    "core_five_year_irr": _r["core_five_year_irr"],
                                    "coc": _r.get("coc"),
                                    "equity_multiple": _r.get("equity_multiple"),
                                    "_delta": _delta,
                                })

            if not _found:
                st.warning("No realistic scenario found using the selected investor targets and levers.")
            else:
                _found.sort(key=lambda x: x["_delta"])
                _rows = []
                for _i, _s in enumerate(_found[:5], 1):
                    _rows.append({
                        "Scenario": f"#{_i}",
                        "Offer Price": dollars(_s["offer_price"]),
                        "Annual Revenue": dollars(_s["prior_year_annual_income"]),
                        "HOA /mo": dollars(_s["hoa_monthly"]),
                        "Taxes / Ins /mo": dollars(_s["taxes_insurance_monthly"]),
                        "Monthly Net": dollars(_s["monthly_net"]),
                        "DSCR": f"{_s['dscr']:.2f}",
                        "Core IRR": pct(_s["core_five_year_irr"]) if _s["core_five_year_irr"] is not None else "N/A",
                        "CoC": pct(_s["coc"]) if _s["coc"] is not None else "N/A",
                        "Eq. Multiple": f"{_s['equity_multiple']:.2f}" if _s["equity_multiple"] is not None else "N/A",
                    })
                st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)

    _status_defaults = {
        "BUY": "Offer Candidate",
        "REVIEW": "Review",
        "DO NOT BUY": "Do Not Buy",
    }
    _status_options = ["Review", "Do Not Buy", "Offer Candidate", "Under Diligence", "Archived"]
    _default_status = _status_defaults.get(verdict_label, "Review")
    _default_status_idx = _status_options.index(_default_status) if _default_status in _status_options else 0

    deal_status = st.selectbox(
        "Deal Status",
        options=_status_options,
        index=_default_status_idx,
        key="deal_status_input",
    )

    deal_notes = st.text_area(
        "Deal Notes",
        placeholder="Location thoughts, inspection flags, seller motivation, comps…",
        height=100,
        key="deal_notes_input",
    )

    _current_deal_row = {
        "property_address": _property_address,
        "listing_url": _listing_url,
        "market_city": _market_city,
        "ask_price": _ask_price,
        "offer_price": _offer_price,
        "prior_year_annual_income": _prior_year_annual_income,
        "hoa_monthly": _hoa_monthly,
        "taxes_insurance_monthly": _taxes_insurance_monthly,
        "bedrooms": _bedrooms,
        "bathrooms": _bathrooms,
        "square_feet": _square_feet,
        "deal_status": st.session_state.get("deal_status_input", ""),
        "verdict": verdict.get("verdict", ""),
        "monthly_net": results["monthly_net"],
        "dscr": results["dscr"],
        "core_five_year_irr": results["core_five_year_irr"],
        "five_year_irr": results["five_year_irr"],
        "revenue_gap_dollars": results["revenue_gap_dollars"],
        "revenue_gap_pct": results.get("revenue_gap_pct", ""),
        "equity_multiple": results["equity_multiple"],
        "deal_notes": st.session_state.get("deal_notes_input", ""),
    }

    _btn_col1, _btn_col2 = st.columns(2)

    with _btn_col1:
        if st.button("Save Deal", use_container_width=True):
            save_deal_to_csv({
                **_current_deal_row,
                "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            })
            st.session_state.pop("loaded_saved_at", None)
            st.success("Deal saved.")

    with _btn_col2:
        _loaded_key = st.session_state.get("loaded_saved_at")
        if _loaded_key:
            if st.button("Update Loaded Deal", use_container_width=True, type="primary"):
                ok = update_deal_in_csv(_loaded_key, _current_deal_row)
                if ok:
                    st.success("Deal updated.")
                else:
                    st.warning("Could not find the original deal to update. Try saving as a new deal.")

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
    p1.metric("Bedrooms", f"{_bedrooms:g}")
    p2.metric("Bathrooms", f"{_bathrooms:g}")
    p3.metric("Square Feet", f"{_square_feet:,.0f}")
    p4.metric(
        "Price / Sq Ft", dollars(_offer_price / _square_feet) if _square_feet else "N/A"
    )

    if _property_address:
        st.caption(f"Address: {_property_address}")

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
        pct(results["five_year_irr"]) if results["five_year_irr"] is not None else "N/A",
    )
    r2.metric(
        "Core 5-Year IRR",
        pct(results["core_five_year_irr"]) if results["core_five_year_irr"] is not None else "N/A",
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
            ["Year 1", results["monthly_net_year_1"], results["monthly_net_year_1"] * 12],
            ["Year 2", results["monthly_net_year_2"], results["monthly_net_year_2"] * 12],
            ["Year 3", results["monthly_net_year_3"], results["monthly_net_year_3"] * 12],
            ["Year 4+", results["monthly_net_year_4_plus"], results["monthly_net_year_4_plus"] * 12],
        ],
        columns=["Period", "Monthly Net", "Annual Net"],
    )

    st.dataframe(
        cash_flow_table.style.format({"Monthly Net": "${:,.0f}", "Annual Net": "${:,.0f}"}),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Scenario Comparison")

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

st.divider()

with st.expander("Saved Deals", expanded=False):
    saved = load_saved_deals()
    if isinstance(saved, str) and saved == "malformed":
        st.warning("Saved deals file appears malformed and could not be read. Delete saved_deals.csv to reset.")
    elif saved is None:
        st.caption("No deals saved yet. Analyze a deal and click Save Deal.")
    else:
        _status_filter_options = ["All", "Review", "Do Not Buy", "Offer Candidate", "Under Diligence", "Archived"]
        _status_filter = st.selectbox("Filter by Deal Status", options=_status_filter_options, key="saved_deals_filter")

        _display_cols = [
            "saved_at", "deal_status", "property_address", "listing_url", "offer_price",
            "verdict", "monthly_net", "dscr", "core_five_year_irr",
            "revenue_gap_dollars", "deal_notes",
        ]
        _visible_cols = [c for c in _display_cols if c in saved.columns]
        _view = saved[_visible_cols].copy()

        if _status_filter != "All":
            _view = _view[_view["deal_status"] == _status_filter]

        if _view.empty:
            st.caption(f"No deals with status '{_status_filter}'.")
        else:
            _col_config = {}
            if "listing_url" in _view.columns:
                _col_config["listing_url"] = st.column_config.LinkColumn(
                    "Listing",
                    display_text="Open Listing",
                )
            st.dataframe(_view, use_container_width=True, hide_index=True, column_config=_col_config)

            st.caption("Load a saved deal back into the form:")

            def _deal_label(row):
                addr = row.get("property_address", "") or ""
                price = row.get("offer_price", "")
                verdict = row.get("verdict", "")
                saved_at = row.get("saved_at", "")
                addr = "" if (addr is None or (isinstance(addr, float))) else str(addr)
                saved_at = "" if (saved_at is None or (isinstance(saved_at, float))) else str(saved_at)
                verdict = "" if (verdict is None or (isinstance(verdict, float))) else str(verdict)
                label = addr if addr else f"Deal saved {saved_at}"
                if price:
                    try:
                        label += f"  ·  ${float(price):,.0f}"
                    except (ValueError, TypeError):
                        pass
                if verdict:
                    label += f"  ·  {verdict}"
                return label

            _full_saved = load_saved_deals()
            if _full_saved is not None and not (isinstance(_full_saved, str) and _full_saved == "malformed"):
                if _status_filter != "All":
                    _full_filtered = _full_saved[_full_saved["deal_status"] == _status_filter].reset_index(drop=True)
                else:
                    _full_filtered = _full_saved.reset_index(drop=True)

                if not _full_filtered.empty:
                    _labels = [_deal_label(row) for _, row in _full_filtered.iterrows()]
                    _selected_idx = st.selectbox(
                        "Select deal to load",
                        options=range(len(_labels)),
                        format_func=lambda i: _labels[i],
                        key="saved_deal_selector",
                        label_visibility="collapsed",
                    )

                    if st.button("Load Selected Deal", use_container_width=True):
                        _load_row = _full_filtered.iloc[_selected_idx]
                        _loadable = {
                            "property_address": "property_address",
                            "market_city": "market_city",
                            "listing_url": "listing_url",
                            "bedrooms": "bedrooms",
                            "bathrooms": "bathrooms",
                            "square_feet": "square_feet",
                            "prior_year_annual_income": "prior_year_annual_income",
                            "hoa_monthly": "hoa_monthly",
                            "taxes_insurance_monthly": "taxes_insurance_monthly",
                            "utilities_monthly": "utilities_monthly",
                        }
                        _numeric = {"bedrooms", "bathrooms", "square_feet",
                                    "prior_year_annual_income", "hoa_monthly",
                                    "taxes_insurance_monthly", "utilities_monthly",
                                    "ask_price", "offer_price"}
                        for state_key, csv_col in _loadable.items():
                            if csv_col in _load_row.index:
                                val = _load_row[csv_col]
                                if state_key in _numeric:
                                    try:
                                        val = float(val) if val != "" else default_values.get(state_key, 0)
                                    except (ValueError, TypeError):
                                        val = default_values.get(state_key, 0)
                                else:
                                    val = "" if pd.isna(val) else str(val)
                                st.session_state[state_key] = val
                        for price_key, csv_col in [("ask_price", "ask_price"), ("offer_price", "offer_price")]:
                            if csv_col in _load_row.index:
                                try:
                                    st.session_state[price_key] = float(_load_row[csv_col])
                                except (ValueError, TypeError):
                                    pass
                        st.session_state.pop("last_analyzed_deal", None)
                        _row_saved_at = _load_row.get("saved_at", "")
                        st.session_state["loaded_saved_at"] = _row_saved_at if _row_saved_at and not pd.isna(_row_saved_at) else ""
                        st.rerun()
