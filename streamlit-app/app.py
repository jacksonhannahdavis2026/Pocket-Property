import csv
import os
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from underwriting import PropertyInputs, calculate
from scenarios import build_scenarios
from verdicts import evaluate

SAVED_DEALS_PATH = os.path.join(os.path.dirname(__file__), "saved_deals.csv")

SAVED_DEALS_COLUMNS = [
    "saved_at",
    "deal_status",
    "deal_quality",
    "revenue_confidence",
    "max_offer",
    "pass_reason",
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

PROPERTY_STATE_OPTIONS = [
    "",
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
]

STATE_ESCROW_DEFAULTS = {
    "Florida": (0.85, 0.45),
    "Texas": (1.80, 0.35),
    "Tennessee": (0.65, 0.35),
    "Georgia": (0.90, 0.35),
    "Alabama": (0.45, 0.40),
    "Arizona": (0.60, 0.30),
}
DEFAULT_ESCROW_RATES = (1.00, 0.35)

STR_PROFILE_DEFAULTS = {
    "Cabin / Mountain STR": {
        "property_management_fee_pct_input": 20.0,
        "maintenance_capex_pct_input": 6.0,
        "utilities_monthly": 550,
        "cleaning_turnover_monthly": 250,
    },
    "Beach Condo": {
        "property_management_fee_pct_input": 18.0,
        "maintenance_capex_pct_input": 4.0,
        "utilities_monthly": 375,
        "cleaning_turnover_monthly": 200,
    },
    "Lake House": {
        "property_management_fee_pct_input": 18.0,
        "maintenance_capex_pct_input": 5.0,
        "utilities_monthly": 450,
        "cleaning_turnover_monthly": 225,
    },
    "Urban Condo": {
        "property_management_fee_pct_input": 15.0,
        "maintenance_capex_pct_input": 3.0,
        "utilities_monthly": 300,
        "cleaning_turnover_monthly": 150,
    },
    "Suburban Single Family": {
        "property_management_fee_pct_input": 10.0,
        "maintenance_capex_pct_input": 4.0,
        "utilities_monthly": 350,
        "cleaning_turnover_monthly": 150,
    },
    "Luxury STR": {
        "property_management_fee_pct_input": 20.0,
        "maintenance_capex_pct_input": 7.0,
        "utilities_monthly": 750,
        "cleaning_turnover_monthly": 400,
    },
}
STR_PROFILE_OPTIONS = list(STR_PROFILE_DEFAULTS.keys()) + ["Manual"]


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


def load_saved_deals(reverse: bool = True):
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

st.markdown(
    """
    <style>
        :root {
            --pp-bg: #F7F4EE;
            --pp-surface: #FCFBF8;
            --pp-border: #E7E1D7;
            --pp-primary: #355E52;
            --pp-primary-dark: #2E3A36;
            --pp-gold: #C8B28A;
            --pp-text: #2E3A36;
            --pp-muted: #6F7A74;
            --pp-success: #4E7A67;
            --pp-warning: #C89B5A;
            --pp-risk: #B86A5B;
            --pp-info: #5F7480;
        }
        .stApp {
            background: var(--pp-bg);
            color: var(--pp-text);
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }
        .pp-section-header {
            margin: 1.45rem 0 0.6rem;
            padding-top: 0.25rem;
        }
        .pp-section-title {
            margin: 0;
            color: var(--pp-text);
            font-size: 1.22rem;
            font-weight: 700;
            letter-spacing: 0;
        }
        .pp-section-subtitle,
        .pp-muted {
            color: var(--pp-muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .pp-section-subtitle {
            margin-top: 0.2rem;
        }
        .pp-card {
            border: 1px solid var(--pp-border);
            border-radius: 8px;
            background: var(--pp-surface);
            padding: 0.9rem 1rem;
            margin: 0.55rem 0;
            box-shadow: 0 1px 2px rgba(46, 58, 54, 0.05);
        }
        .pp-card-title {
            color: var(--pp-text);
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        .pp-card-body {
            color: var(--pp-muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .pp-score-card {
            border: 1px solid var(--pp-border);
            border-radius: 8px;
            padding: 1rem 1.05rem;
            margin: 0.55rem 0 0.85rem;
            box-shadow: 0 1px 2px rgba(46, 58, 54, 0.05);
        }
        .pp-score-card-success {
            background: linear-gradient(180deg, rgba(78, 122, 103, 0.12), rgba(252, 251, 248, 0.92));
            border-color: rgba(78, 122, 103, 0.26);
        }
        .pp-score-card-warning {
            background: linear-gradient(180deg, rgba(200, 155, 90, 0.14), rgba(252, 251, 248, 0.92));
            border-color: rgba(200, 155, 90, 0.30);
        }
        .pp-score-card-danger {
            background: linear-gradient(180deg, rgba(184, 106, 91, 0.13), rgba(252, 251, 248, 0.92));
            border-color: rgba(184, 106, 91, 0.30);
        }
        .pp-score-top {
            display: flex;
            align-items: baseline;
            gap: 0.45rem;
            flex-wrap: wrap;
        }
        .pp-score-value {
            color: var(--pp-primary-dark);
            font-size: 2.35rem;
            line-height: 1;
            font-weight: 800;
            letter-spacing: 0;
        }
        .pp-score-out-of {
            color: var(--pp-muted);
            font-size: 1rem;
            font-weight: 650;
        }
        .pp-score-label {
            color: var(--pp-text);
            font-size: 1.05rem;
            font-weight: 750;
            margin-top: 0.35rem;
        }
        .pp-score-explanation {
            color: var(--pp-muted);
            font-size: 0.92rem;
            line-height: 1.45;
            margin-top: 0.25rem;
        }
        .pp-score-track {
            height: 0.58rem;
            border-radius: 999px;
            background: rgba(46, 58, 54, 0.10);
            overflow: hidden;
            margin-top: 0.85rem;
        }
        .pp-score-fill {
            height: 100%;
            border-radius: 999px;
        }
        .pp-score-fill-success {
            background: var(--pp-success);
        }
        .pp-score-fill-warning {
            background: var(--pp-warning);
        }
        .pp-score-fill-danger {
            background: var(--pp-risk);
        }
        .pp-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.28rem 0.72rem;
            font-size: 0.86rem;
            font-weight: 700;
            letter-spacing: 0;
            border: 1px solid transparent;
            margin: 0.15rem 0 0.45rem;
        }
        .pp-badge-info {
            background: rgba(95, 116, 128, 0.12);
            color: var(--pp-info);
            border-color: rgba(95, 116, 128, 0.28);
        }
        .pp-badge-success {
            background: rgba(78, 122, 103, 0.12);
            color: var(--pp-success);
            border-color: rgba(78, 122, 103, 0.28);
        }
        .pp-badge-warning {
            background: rgba(200, 155, 90, 0.14);
            color: var(--pp-warning);
            border-color: rgba(200, 155, 90, 0.32);
        }
        .pp-badge-danger {
            background: rgba(184, 106, 91, 0.13);
            color: var(--pp-risk);
            border-color: rgba(184, 106, 91, 0.32);
        }
        div[data-testid="stMetric"] {
            border: 1px solid var(--pp-border);
            border-radius: 8px;
            padding: 0.75rem 0.85rem;
            background: var(--pp-surface);
            box-shadow: 0 1px 2px rgba(46, 58, 54, 0.04);
        }
        div[data-testid="stMetricLabel"] {
            color: var(--pp-muted);
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        h1 {
            color: var(--pp-primary-dark);
        }
        div[data-testid="stForm"] {
            border-color: var(--pp-border);
            background: rgba(252, 251, 248, 0.64);
        }
        .stButton > button,
        div[data-testid="stLinkButton"] a {
            border-radius: 8px;
            font-weight: 650;
        }
        button[kind="primary"] {
            background: var(--pp-primary);
            border-color: var(--pp-primary);
            color: var(--pp-surface);
        }
        button[kind="primary"]:hover {
            background: var(--pp-primary-dark);
            border-color: var(--pp-primary-dark);
            color: var(--pp-surface);
        }
        div[data-testid="stLinkButton"] a {
            border-color: var(--pp-border);
            color: var(--pp-primary-dark);
            background: var(--pp-surface);
        }
        div[data-testid="stLinkButton"] a:hover {
            border-color: var(--pp-gold);
            color: var(--pp-primary-dark);
            background: rgba(200, 178, 138, 0.14);
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def section_header(title, subtitle=None):
    subtitle_html = (
        f'<div class="pp-section-subtitle">{escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div class="pp-section-header">
            <h2 class="pp-section-title">{escape(title)}</h2>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_card(title, body=None):
    body_html = f'<div class="pp-card-body">{escape(body)}</div>' if body else ""
    st.markdown(
        f"""
        <div class="pp-card">
            <div class="pp-card-title">{escape(title)}</div>
            {body_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(label, status="info"):
    status_class = {
        "success": "pp-badge-success",
        "warning": "pp-badge-warning",
        "danger": "pp-badge-danger",
        "info": "pp-badge-info",
    }.get(status, "pp-badge-info")
    st.markdown(
        f'<span class="pp-badge {status_class}">{escape(label)}</span>',
        unsafe_allow_html=True,
    )


def muted_text(text):
    st.markdown(f'<div class="pp-muted">{escape(text)}</div>', unsafe_allow_html=True)


def score_progress_status(score):
    if score >= 75:
        return "success"
    if score >= 50:
        return "warning"
    return "danger"


def deal_score_card(score, label, explanation):
    status = score_progress_status(score)
    safe_score = max(0, min(100, int(score)))
    st.markdown(
        f"""
        <div class="pp-score-card pp-score-card-{status}">
            <div class="pp-score-top">
                <div class="pp-score-value">{safe_score}</div>
                <div class="pp-score-out-of">/ 100</div>
            </div>
            <div class="pp-score-label">{escape(str(label))}</div>
            <div class="pp-score-explanation">{escape(str(explanation))}</div>
            <div class="pp-score-track">
                <div class="pp-score-fill pp-score-fill-{status}" style="width: {safe_score}%;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_explainer(label, what_it_means, why_it_matters, good_range=None):
    with st.expander(f"What does {label} mean?"):
        st.markdown(f"**What it means:** {what_it_means}")
        st.markdown(f"**Why it matters:** {why_it_matters}")
        if good_range:
            st.markdown(f"**Generally good:** {good_range}")


st.title("Property Pocket")
muted_text("Fast acquisition screen for STR / rental property underwriting.")


def dollars(value):
    return f"${value:,.0f}"


def dollars_month(value):
    return f"${value:,.0f}/mo"


def pct(value):
    return f"{value:.1%}"


def multiple(value):
    return f"{value:.2f}x"


def parse_currency_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    cleaned = str(value).strip()
    if not cleaned:
        return None

    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if cleaned in {"", "-", ".", "-."}:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def format_currency_value(value, blank_zero=False):
    parsed = parse_currency_value(value)
    if parsed is None:
        return ""
    if blank_zero and parsed == 0:
        return ""
    return f"${parsed:,.0f}"


def currency_input(label, key, help=None, allow_none=False, blank_zero=False):
    display_key = f"{key}_currency_display"
    shadow_key = f"{key}_currency_value"
    st.session_state[f"{key}_currency_allow_none"] = allow_none
    st.session_state[f"{key}_currency_blank_zero"] = blank_zero
    canonical_value = st.session_state.get(key)
    expected_display = format_currency_value(canonical_value, blank_zero=blank_zero)
    current_display = st.session_state.get(display_key)

    if (
        display_key not in st.session_state
        or st.session_state.get(shadow_key) != canonical_value
        or st.session_state.get(f"{key}_needs_currency_format")
        or (
            current_display != expected_display
            and parse_currency_value(current_display) == parse_currency_value(canonical_value)
        )
    ):
        st.session_state[display_key] = expected_display
        st.session_state[shadow_key] = canonical_value

    raw_value = st.text_input(label, key=display_key, help=help)
    parsed = parse_currency_value(raw_value)
    numeric_value = None if allow_none and parsed is None else (parsed or 0)
    formatted_value = format_currency_value(numeric_value, blank_zero=blank_zero)

    st.session_state[key] = numeric_value
    st.session_state[shadow_key] = numeric_value
    if raw_value != formatted_value and parse_currency_value(raw_value) == parse_currency_value(numeric_value):
        st.session_state[f"{key}_needs_currency_format"] = True
    else:
        st.session_state.pop(f"{key}_needs_currency_format", None)
    return numeric_value


def normalize_currency_input_displays():
    display_keys = [
        key for key in list(st.session_state.keys())
        if key.endswith("_currency_display")
    ]
    for display_key in display_keys:
        base_key = display_key[: -len("_currency_display")]
        allow_none = st.session_state.get(f"{base_key}_currency_allow_none", False)
        blank_zero = st.session_state.get(f"{base_key}_currency_blank_zero", False)
        parsed = parse_currency_value(st.session_state.get(display_key))
        numeric_value = None if allow_none and parsed is None else (parsed or 0)

        st.session_state[base_key] = numeric_value
        st.session_state[f"{base_key}_currency_value"] = numeric_value
        st.session_state[display_key] = format_currency_value(
            numeric_value,
            blank_zero=blank_zero,
        )
        st.session_state.pop(f"{base_key}_needs_currency_format", None)


def revenue_gap_display(results):
    gap = results.get("revenue_gap_dollars", 0) or 0
    if gap > 0:
        return {
            "label": "Revenue Needed",
            "value": dollars(gap),
            "status": "danger",
            "text": "This deal still needs more annual revenue to hit the target.",
        }
    cushion = abs(gap)
    return {
        "label": "Revenue Cushion",
        "value": f"+{dollars(cushion)}",
        "status": "success",
        "text": "Current revenue assumptions exceed the target revenue need.",
    }


PIPELINE_STATUSES = ["Analyzing", "Interested", "Offer Ready", "Under Contract", "Passed"]
PASS_REASONS = [
    "",
    "Revenue too aggressive",
    "DSCR too weak",
    "HOA too high",
    "Taxes / insurance too high",
    "Overpaying risk",
    "STR regulation concern",
    "Better opportunities elsewhere",
    "Other",
]


def normalize_pipeline_status(status):
    status = "" if pd.isna(status) else str(status).strip()
    legacy_map = {
        "Review": "Analyzing",
        "Do Not Buy": "Passed",
        "Offer Candidate": "Offer Ready",
        "Under Diligence": "Interested",
        "Archived": "Passed",
    }
    status = legacy_map.get(status, status)
    return status if status in PIPELINE_STATUSES else "Analyzing"


def revenue_confidence_label(revenue_gap_pct):
    try:
        gap = float(revenue_gap_pct)
    except (TypeError, ValueError):
        return "Unknown"
    if gap < 0.15:
        return "High"
    if gap <= 0.30:
        return "Medium"
    return "Low"


def confidence_status(confidence):
    return {
        "High": "success",
        "Medium": "warning",
        "Low": "danger",
    }.get(confidence, "info")


def quality_status(quality):
    return {
        "STRONG": "success",
        "FIXABLE": "warning",
        "UNREALISTIC": "danger",
    }.get(str(quality), "info")


def safe_text(value, fallback=""):
    if value is None or pd.isna(value):
        return fallback
    value = str(value).strip()
    return value if value else fallback


def safe_float(value, default=0):
    try:
        if value is None or pd.isna(value) or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def search_url(query):
    return f"https://www.google.com/search?q={quote_plus(query)}"


def extract_location_parts(property_address, market_city):
    location = {"city": market_city or "", "state": ""}
    if not property_address:
        return location

    match = re.search(r",\s*([^,]+),\s*([A-Z]{2})\s+\d{5}", property_address)
    if match:
        location["city"] = match.group(1).strip()
        location["state"] = match.group(2).strip()
        return location

    state_match = re.search(r"\b([A-Z]{2})\s+\d{5}\b", property_address)
    if state_match:
        location["state"] = state_match.group(1).strip()

    return location


def build_due_diligence_links(property_address, market_city):
    location = extract_location_parts(property_address, market_city)
    city_state = " ".join(
        part for part in [location["city"], location["state"]] if part
    )
    property_query = property_address or city_state or "property"

    return [
        {
            "label": "County Appraisal District",
            "url": search_url(
                f"{city_state} county appraisal district property search {property_query}"
            ),
            "note": "Find assessed value, ownership, parcel ID, and appraisal history.",
        },
        {
            "label": "Property Search",
            "url": search_url(f"{property_query} county property search"),
            "note": "Confirm parcel details, legal description, beds/baths, and square footage.",
        },
        {
            "label": "Tax Records",
            "url": search_url(f"{property_query} property tax records county tax collector"),
            "note": "Check current taxes, exemptions, delinquencies, and recent tax changes.",
        },
        {
            "label": "Recorded Deeds",
            "url": search_url(f"{city_state} county recorder official records deeds {property_query}"),
            "note": "Review sale history, deed transfers, liens, and recorded documents.",
        },
    ]


def market_reality_label(delta_pct, metric_name):
    if delta_pct is None:
        return f"Add {metric_name.lower()} comp", "info"

    if metric_name == "Revenue":
        if delta_pct < 0:
            return "Revenue looks conservative", "success"
        if delta_pct <= 0.10:
            return "Revenue looks grounded", "success"
        if delta_pct <= 0.25:
            return "Revenue needs support", "warning"
        return "Revenue needs strong proof", "danger"

    if abs(delta_pct) <= 0.10:
        return f"{metric_name} looks grounded", "success"
    if abs(delta_pct) <= 0.25:
        return f"{metric_name} needs support", "warning"
    return f"{metric_name} is stretched", "danger"


def market_reality_interpretation(revenue_delta_pct, price_delta_pct):
    if revenue_delta_pct is None and price_delta_pct is None:
        return "Enter at least one nearby comp to pressure-test the current assumptions."
    if revenue_delta_pct is not None and revenue_delta_pct > 0.25:
        return "Revenue is materially above the comp. Do not rely on this assumption without strong source support."
    if price_delta_pct is not None and price_delta_pct > 0.25:
        return "The offer is materially above the sold comp. Confirm quality, location, and revenue differences before proceeding."
    if revenue_delta_pct is not None and revenue_delta_pct < 0:
        return "Revenue is below the comp, which is a more conservative starting point. Still confirm the comp quality before relying on it."
    if (
        revenue_delta_pct is not None
        and price_delta_pct is not None
        and abs(revenue_delta_pct) <= 0.10
        and abs(price_delta_pct) <= 0.10
    ):
        return "Revenue and offer assumptions are close to the comp. This does not prove the deal, but it lowers assumption risk."
    return "The assumptions are within a reviewable range. Validate the comp quality before treating this as offer support."


def offer_position_label(offer_price, annual_revenue):
    if not offer_price or not annual_revenue:
        return None

    low_value = annual_revenue / 0.10
    high_value = annual_revenue / 0.07
    if offer_price < low_value:
        return "below_range"
    if offer_price <= high_value:
        return "within_range"
    return "above_range"


def deal_score_label(score):
    if score >= 85:
        return "Elite"
    if score >= 70:
        return "Strong"
    if score >= 55:
        return "Workable"
    if score >= 40:
        return "Risky"
    return "Avoid"


def cap_score_for_revenue_premium(score, revenue_premium_pct):
    if revenue_premium_pct is None or revenue_premium_pct <= 0.35:
        return score
    if revenue_premium_pct <= 0.50:
        return min(score, 69)
    return min(score, 54)


def display_verdict_label(verdict_label, revenue_premium_pct=None):
    if verdict_label == "DO NOT BUY":
        return "DO NOT BUY"
    if revenue_premium_pct is not None and revenue_premium_pct > 0.35:
        return "SPECULATIVE"
    return verdict_label


def deal_score_status(label):
    if label in {"Elite", "Strong"}:
        return "success"
    if label in {"Workable", "Risky"}:
        return "warning"
    return "danger"


def deal_score_explanation(score_label, revenue_realism_label=None, offer_position=None):
    if revenue_realism_label == "Revenue needs strong proof":
        return "Revenue is materially above nearby comp support. Treat this as speculative until stronger proof is available."
    if score_label in {"Elite", "Strong"}:
        if revenue_realism_label in {"Revenue needs support", "Revenue needs strong proof"}:
            return "This deal clears many core investor targets, but revenue assumptions still need verification."
        if offer_position == "above_range":
            return "This deal has attractive metrics, but the offer needs value discipline before proceeding."
        return "This deal clears most core investor targets and looks disciplined on the current assumptions."

    if score_label == "Workable":
        return "This deal may be workable, but it needs careful validation before it can support a confident offer."
    if score_label == "Risky":
        return "This deal is below target in important areas. Continue only if realistic improvements are available."
    return "This deal does not currently support a disciplined offer without major assumption changes."


def calculate_deal_score(
    dscr,
    monthly_net,
    core_irr,
    revenue_gap,
    annual_revenue,
    revenue_realism_label=None,
    revenue_premium_pct=None,
    offer_position=None,
):
    score = 0

    if dscr is None:
        score += 8
    elif dscr >= 1.25:
        score += 25
    elif dscr >= 1.00:
        score += 18
    elif dscr >= 0.80:
        score += 10
    else:
        score += 3

    if monthly_net is None:
        score += 6
    elif monthly_net >= 1000:
        score += 20
    elif monthly_net >= 500:
        score += 15
    elif monthly_net >= 0:
        score += 9
    else:
        score += 2

    if core_irr is None:
        score += 6
    elif core_irr >= 0.18:
        score += 20
    elif core_irr >= 0.12:
        score += 15
    elif core_irr >= 0.08:
        score += 9
    else:
        score += 2

    if revenue_gap is None:
        score += 7
    elif revenue_gap <= 0:
        score += 15
    elif annual_revenue and annual_revenue > 0:
        gap_pct = revenue_gap / annual_revenue
        if gap_pct < 0.10:
            score += 10
        elif gap_pct <= 0.25:
            score += 5
        else:
            score += 1
    else:
        score += 3

    if revenue_premium_pct is not None and revenue_premium_pct > 0.50:
        score -= 18
    elif revenue_premium_pct is not None and revenue_premium_pct > 0.35:
        score -= 12
    elif revenue_premium_pct is not None and revenue_premium_pct > 0.20:
        score -= 7
    elif revenue_premium_pct is not None and revenue_premium_pct > 0.10:
        score -= 3

    if revenue_realism_label in {"Revenue looks conservative", "Revenue looks grounded"}:
        score += 10
    elif revenue_realism_label == "Revenue needs support":
        score += 5
    elif revenue_realism_label == "Revenue needs strong proof":
        score += 1
    else:
        score += 6

    if offer_position == "below_range":
        score += 10
    elif offer_position == "within_range":
        score += 6
    elif offer_position == "above_range":
        score += 1
    else:
        score += 6

    score = max(0, min(100, int(round(score))))
    return cap_score_for_revenue_premium(score, revenue_premium_pct)


def estimate_monthly_taxes_insurance(purchase_price, property_tax_rate_pct, insurance_rate_pct):
    if not purchase_price:
        return 0
    property_tax_rate = (property_tax_rate_pct or 0) / 100
    insurance_rate = (insurance_rate_pct or 0) / 100
    monthly_property_tax = (purchase_price * property_tax_rate) / 12
    monthly_insurance = (purchase_price * insurance_rate) / 12
    return monthly_property_tax + monthly_insurance


def apply_profile_defaults(profile):
    if profile == "Manual" or profile not in STR_PROFILE_DEFAULTS:
        return
    for key, value in STR_PROFILE_DEFAULTS[profile].items():
        st.session_state[key] = value
    st.session_state["str_profile_applied"] = profile


def build_qa_property_inputs(**overrides):
    defaults = {
        "ask_price": 600000,
        "offer_price": 575000,
        "down_payment_pct": 0.20,
        "interest_rate": 0.0675,
        "prior_year_annual_income": 90000,
        "loan_term_years": 30,
        "case_scenario": "Base",
        "hoa_monthly": 450,
        "taxes_insurance_monthly": 950,
        "utilities_monthly": 250,
        "county_appraisal_value": 575000,
        "land_allocation_pct": 0.20,
        "five_year_asset_pct": 0.10,
        "seven_year_asset_pct": 0.03,
        "fifteen_year_asset_pct": 0.07,
        "twenty_seven_half_year_asset_pct": 0.80,
        "annual_w2_income": 354000,
        "closing_costs": 12000,
        "annual_market_appreciation": 0.02,
        "annual_rent_appreciation": 0.02,
        "cost_to_sell_pct": 0.03,
        "depreciation_recapture_tax_rate": 0.25,
        "target_dscr": 1.00,
    }
    defaults.update(overrides)
    return PropertyInputs(**defaults)


def run_qa_scenarios():
    qa_cases = [
        {
            "Scenario": "Elite deal",
            "comp_revenue": 100000,
            "inputs": build_qa_property_inputs(
                offer_price=500000,
                prior_year_annual_income=125000,
                hoa_monthly=250,
                taxes_insurance_monthly=650,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Strong deal",
            "comp_revenue": 90000,
            "inputs": build_qa_property_inputs(
                offer_price=560000,
                prior_year_annual_income=98000,
                hoa_monthly=400,
                taxes_insurance_monthly=850,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Borderline",
            "comp_revenue": 80000,
            "inputs": build_qa_property_inputs(
                offer_price=625000,
                prior_year_annual_income=78000,
                hoa_monthly=650,
                taxes_insurance_monthly=1050,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Unrealistic",
            "comp_revenue": 70000,
            "inputs": build_qa_property_inputs(
                offer_price=800000,
                prior_year_annual_income=62000,
                hoa_monthly=1200,
                taxes_insurance_monthly=1600,
                case_scenario="Conservative",
            ),
        },
        {
            "Scenario": "Aggressive revenue",
            "comp_revenue": 76000,
            "inputs": build_qa_property_inputs(
                offer_price=620000,
                prior_year_annual_income=115000,
                hoa_monthly=500,
                taxes_insurance_monthly=900,
                case_scenario="Aggressive",
            ),
        },
        {
            "Scenario": "Low DSCR",
            "comp_revenue": 85000,
            "inputs": build_qa_property_inputs(
                offer_price=700000,
                prior_year_annual_income=80000,
                hoa_monthly=500,
                taxes_insurance_monthly=1150,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Negative cash flow",
            "comp_revenue": 90000,
            "inputs": build_qa_property_inputs(
                offer_price=690000,
                prior_year_annual_income=85000,
                hoa_monthly=1450,
                taxes_insurance_monthly=1400,
                utilities_monthly=350,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "High IRR / Weak DSCR",
            "comp_revenue": 90000,
            "note": "Exit gains may be masking weak debt coverage.",
            "inputs": build_qa_property_inputs(
                offer_price=720000,
                prior_year_annual_income=82000,
                hoa_monthly=850,
                taxes_insurance_monthly=1250,
                annual_market_appreciation=0.08,
                case_scenario="Aggressive",
            ),
        },
        {
            "Scenario": "Positive Cash Flow / Overpriced",
            "comp_revenue": 115000,
            "note": "Monthly net is positive, but basis may be too high.",
            "inputs": build_qa_property_inputs(
                offer_price=940000,
                prior_year_annual_income=118000,
                hoa_monthly=300,
                taxes_insurance_monthly=900,
                annual_market_appreciation=0.00,
                case_scenario="Aggressive",
            ),
        },
        {
            "Scenario": "Cheap Property / Weak Revenue",
            "comp_revenue": 48000,
            "note": "Low price does not automatically solve weak operations.",
            "inputs": build_qa_property_inputs(
                offer_price=280000,
                prior_year_annual_income=42000,
                hoa_monthly=900,
                taxes_insurance_monthly=650,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Tax Shelter Illusion",
            "comp_revenue": 80000,
            "note": "Tax-enhanced return may overpower weak fundamentals.",
            "inputs": build_qa_property_inputs(
                offer_price=780000,
                prior_year_annual_income=76000,
                hoa_monthly=1250,
                taxes_insurance_monthly=1400,
                county_appraisal_value=950000,
                five_year_asset_pct=0.22,
                seven_year_asset_pct=0.08,
                fifteen_year_asset_pct=0.15,
                annual_w2_income=650000,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Strong DSCR / Aggressive Revenue",
            "comp_revenue": 85000,
            "note": "Strong DSCR depends on revenue well above comp support.",
            "inputs": build_qa_property_inputs(
                offer_price=520000,
                prior_year_annual_income=122000,
                hoa_monthly=250,
                taxes_insurance_monthly=650,
                case_scenario="Aggressive",
            ),
        },
        {
            "Scenario": "Strong Operations / Weak Exit",
            "comp_revenue": 90000,
            "note": "Operations look healthy, but exit economics are muted.",
            "inputs": build_qa_property_inputs(
                offer_price=610000,
                prior_year_annual_income=90000,
                hoa_monthly=250,
                taxes_insurance_monthly=700,
                annual_market_appreciation=-0.02,
                cost_to_sell_pct=0.08,
                case_scenario="Base",
            ),
        },
        {
            "Scenario": "Safe but Boring",
            "comp_revenue": 82000,
            "note": "Stable assumptions with limited upside.",
            "inputs": build_qa_property_inputs(
                offer_price=540000,
                prior_year_annual_income=76000,
                hoa_monthly=300,
                taxes_insurance_monthly=650,
                annual_market_appreciation=0.00,
                annual_rent_appreciation=0.00,
                case_scenario="Conservative",
            ),
        },
    ]

    rows = []
    for case in qa_cases:
        inputs = case["inputs"]
        results = calculate(inputs)
        verdict = evaluate(results)
        revenue_delta_pct = (
            (inputs.prior_year_annual_income - case["comp_revenue"]) / case["comp_revenue"]
            if case["comp_revenue"]
            else None
        )
        revenue_realism_label, _ = market_reality_label(revenue_delta_pct, "Revenue")
        offer_position = offer_position_label(inputs.offer_price, inputs.prior_year_annual_income)
        score = calculate_deal_score(
            dscr=results.get("dscr"),
            monthly_net=results.get("monthly_net"),
            core_irr=results.get("core_five_year_irr"),
            revenue_gap=results.get("revenue_gap_dollars"),
            annual_revenue=inputs.prior_year_annual_income,
            revenue_realism_label=revenue_realism_label,
            revenue_premium_pct=revenue_delta_pct,
            offer_position=offer_position,
        )

        display_verdict = display_verdict_label(
            verdict["verdict"],
            revenue_delta_pct,
        )
        flags = []
        if revenue_delta_pct is not None and revenue_delta_pct > 0.35:
            flags.append("REV_AGGRESSIVE")
        if (score >= 70 and display_verdict == "DO NOT BUY") or (
            score < 40 and display_verdict == "BUY"
        ):
            flags.append("Conflicting logic")
        if (
            score >= 70
            and (
                results.get("dscr", 0) < 1.00
                or results.get("monthly_net", 0) < 0
                or (results.get("core_five_year_irr") is not None and results.get("core_five_year_irr") < 0.08)
                or results.get("revenue_gap_pct", 0) > 0.25
            )
        ):
            flags.append("Unrealistic strong score")
        if (
            results.get("five_year_irr") is not None
            and results.get("five_year_irr") >= 0.25
            and (
                results.get("core_five_year_irr") is None
                or results.get("core_five_year_irr") < 0.08
            )
        ):
            flags.append("Tax IRR overpowering weak core")
        if results.get("dscr", 0) < 1.00 and (
            results.get("core_five_year_irr") is not None
            and results.get("core_five_year_irr") > 0.08
        ):
            flags.append("IRR_DSCR_CONFLICT")
        if results.get("monthly_net", 0) > 0 and (
            results.get("core_five_year_irr") is None
            or results.get("core_five_year_irr") < 0.08
        ):
            flags.append("CASHFLOW_EXIT_CONFLICT")

        rows.append(
            {
                "Scenario": case["Scenario"],
                "Score": score,
                "DSCR": f"{results.get('dscr', 0):.2f}",
                "Monthly Net": dollars_month(results.get("monthly_net", 0)),
                "Core IRR": pct(results["core_five_year_irr"]) if results.get("core_five_year_irr") is not None else "N/A",
                "Tax IRR": pct(results["five_year_irr"]) if results.get("five_year_irr") is not None else "N/A",
                "Verdict": display_verdict,
                "Revenue Gap": dollars(results.get("revenue_gap_dollars", 0)),
                "Revenue Premium": f"{revenue_delta_pct:+.1%}" if revenue_delta_pct is not None else "N/A",
                "Flags": ", ".join(flags) if flags else "OK",
                "Note": case.get("note", ""),
            }
        )

    return rows


def score_bucket(score):
    return deal_score_label(score)


def sweep_values(start_value, end_value, step_count):
    count = max(2, int(step_count or 2))
    if count == 1:
        return [start_value]
    step = (end_value - start_value) / (count - 1)
    return [start_value + (step * i) for i in range(count)]


def format_sweep_value(variable, value):
    if variable in {"Annual Revenue", "Offer Price", "Nightly Rate"}:
        return dollars(value)
    if variable in {"Interest Rate", "Occupancy", "Exit Cap Rate", "Property Tax Rate"}:
        return f"{value:.2f}%"
    return f"{value:,.2f}"


def sensitivity_default_range(variable, base_inputs, base_occupancy_pct, base_nightly_rate, base_tax_rate):
    if variable == "Annual Revenue":
        base = base_inputs.prior_year_annual_income or 80000
        return base * 0.70, base * 1.30
    if variable == "Offer Price":
        base = base_inputs.offer_price or base_inputs.ask_price or 600000
        return base * 0.85, base * 1.15
    if variable == "Interest Rate":
        return 5.00, 9.00
    if variable == "Occupancy":
        return max(20.0, base_occupancy_pct - 20), min(95.0, base_occupancy_pct + 20)
    if variable == "Nightly Rate":
        base = base_nightly_rate or 350
        return base * 0.75, base * 1.25
    if variable == "Exit Cap Rate":
        return 5.00, 10.00
    if variable == "Property Tax Rate":
        base = base_tax_rate or 1.00
        return max(0.10, base - 0.75), base + 0.75
    return 0.0, 1.0


def run_sensitivity_sweep(
    base_inputs,
    variable,
    start_value,
    end_value,
    step_count,
    comp_revenue=None,
    base_occupancy_pct=60.0,
    base_nightly_rate=None,
    insurance_rate_pct=0.35,
):
    rows = []
    previous = None
    base_kwargs = base_inputs.__dict__.copy()
    base_occupancy = max((base_occupancy_pct or 60.0) / 100, 0.01)
    base_nightly = base_nightly_rate or (
        base_inputs.prior_year_annual_income / (365 * base_occupancy)
        if base_inputs.prior_year_annual_income
        else 0
    )

    for value in sweep_values(start_value, end_value, step_count):
        scenario_kwargs = base_kwargs.copy()

        if variable == "Annual Revenue":
            scenario_kwargs["prior_year_annual_income"] = value
        elif variable == "Offer Price":
            scenario_kwargs["offer_price"] = value
        elif variable == "Interest Rate":
            scenario_kwargs["interest_rate"] = value / 100
        elif variable == "Occupancy":
            scenario_kwargs["prior_year_annual_income"] = base_nightly * 365 * (value / 100)
        elif variable == "Nightly Rate":
            scenario_kwargs["prior_year_annual_income"] = value * 365 * base_occupancy
        elif variable == "Exit Cap Rate":
            temp_results = calculate(PropertyInputs(**scenario_kwargs))
            exit_cap = max(value / 100, 0.001)
            target_sale_value = temp_results.get("noi", 0) / exit_cap
            if scenario_kwargs["offer_price"] and target_sale_value > 0:
                scenario_kwargs["annual_market_appreciation"] = (
                    (target_sale_value / scenario_kwargs["offer_price"]) ** (1 / 5)
                ) - 1
        elif variable == "Property Tax Rate":
            purchase_price = scenario_kwargs.get("offer_price") or scenario_kwargs.get("ask_price")
            scenario_kwargs["taxes_insurance_monthly"] = estimate_monthly_taxes_insurance(
                purchase_price,
                value,
                insurance_rate_pct,
            )

        scenario_inputs = PropertyInputs(**scenario_kwargs)
        results = calculate(scenario_inputs)
        verdict = evaluate(results)
        revenue_delta_pct = (
            (scenario_inputs.prior_year_annual_income - comp_revenue) / comp_revenue
            if comp_revenue
            else None
        )
        revenue_realism_label, _ = market_reality_label(revenue_delta_pct, "Revenue")
        offer_position = offer_position_label(
            scenario_inputs.offer_price,
            scenario_inputs.prior_year_annual_income,
        )
        score = calculate_deal_score(
            dscr=results.get("dscr"),
            monthly_net=results.get("monthly_net"),
            core_irr=results.get("core_five_year_irr"),
            revenue_gap=results.get("revenue_gap_dollars"),
            annual_revenue=scenario_inputs.prior_year_annual_income,
            revenue_realism_label=revenue_realism_label,
            revenue_premium_pct=revenue_delta_pct,
            offer_position=offer_position,
        )
        display_verdict = display_verdict_label(verdict["verdict"], revenue_delta_pct)
        core_irr = results.get("core_five_year_irr")

        flags = []
        if previous:
            if previous["Verdict"] != display_verdict:
                flags.append("VERDICT_CHANGE")
            if previous["Score Bucket"] != score_bucket(score):
                flags.append("SCORE_BUCKET_CHANGE")
            if (previous["DSCR Raw"] < 1.0 <= results["dscr"]) or (
                previous["DSCR Raw"] >= 1.0 > results["dscr"]
            ):
                flags.append("DSCR_BREAK")
            if (previous["Monthly Net Raw"] < 0 <= results["monthly_net"]) or (
                previous["Monthly Net Raw"] >= 0 > results["monthly_net"]
            ):
                flags.append("CASHFLOW_BREAK")
            prev_irr = previous["Core IRR Raw"]
            if prev_irr is not None and core_irr is not None and (
                (prev_irr < 0.10 <= core_irr) or (prev_irr >= 0.10 > core_irr)
            ):
                flags.append("IRR_BREAK")

        row = {
            "Sweep Raw": value,
            "Sweep Value": format_sweep_value(variable, value),
            "Score": score,
            "Score Bucket": score_bucket(score),
            "DSCR": f"{results['dscr']:.2f}",
            "DSCR Raw": results["dscr"],
            "Core IRR": pct(core_irr) if core_irr is not None else "N/A",
            "Core IRR Raw": core_irr,
            "Monthly Net": dollars_month(results["monthly_net"]),
            "Monthly Net Raw": results["monthly_net"],
            "Revenue Needed": dollars(max(results.get("revenue_gap_dollars", 0), 0)),
            "Revenue Needed Raw": max(results.get("revenue_gap_dollars", 0), 0),
            "Verdict": display_verdict,
            "Revenue Premium": f"{revenue_delta_pct:+.1%}" if revenue_delta_pct is not None else "N/A",
            "Revenue Premium Raw": revenue_delta_pct,
            "Flags": ", ".join(flags) if flags else "",
        }
        rows.append(row)
        previous = row

    return rows


def sensitivity_insights(rows, variable):
    insights = []
    for row in rows:
        if row["Monthly Net Raw"] >= 0:
            insights.append(f"Deal becomes cash flow positive at {row['Sweep Value']}.")
            break
    for row in rows:
        if row["DSCR Raw"] < 1.0:
            insights.append(f"DSCR falls below 1.0 at {row['Sweep Value']}.")
            break
    for row in rows:
        if "VERDICT_CHANGE" in row["Flags"]:
            insights.append(f"Verdict changes to {row['Verdict']} at {row['Sweep Value']}.")
            break
    for row in rows:
        if row["Revenue Premium Raw"] is not None and row["Revenue Premium Raw"] > 0.35:
            insights.append(
                f"Revenue premium exceeds 35% at {row['Sweep Value']}, triggering speculative revenue risk."
            )
            break
    if not insights:
        insights.append(f"No major score, DSCR, cash flow, IRR, or verdict cliffs detected across this {variable} sweep.")
    return insights


def build_before_offer_checklist(
    deal_tier,
    results,
    offer_price,
    annual_revenue,
    hoa_monthly,
):
    checklist = [
        "Validate nearby sale comps against the current offer price.",
        "Confirm HOA rules, city/county STR restrictions, insurance, and lender requirements.",
    ]

    revenue_gap_pct = results.get("revenue_gap_pct")
    monthly_net = results.get("monthly_net", 0)
    dscr = results.get("dscr", 0)
    core_irr = results.get("core_five_year_irr")

    if annual_revenue and annual_revenue > 0:
        low_value = annual_revenue / 0.10
        high_value = annual_revenue / 0.07

        if offer_price > high_value:
            checklist.append(
                "Watch overpaying risk: the offer is above the implied value range from current revenue."
            )
        elif offer_price < low_value:
            checklist.append(
                "Prepare support for an aggressive below-market offer using revenue, expense, and comp data."
            )
        else:
            checklist.append(
                "Verify the offer still sits inside the implied value range after updated revenue proof."
            )
    else:
        checklist.append("Add a credible annual revenue estimate before making an offer.")

    if revenue_gap_pct is not None:
        if revenue_gap_pct <= 0:
            checklist.append(
                "Revenue clears the target today, but still validate source quality before offering."
            )
        elif revenue_gap_pct > 0.30:
            checklist.append(
                "Do not rely on upside revenue without third-party STR data, owner statements, or strong comps."
            )
        elif revenue_gap_pct >= 0.15:
            checklist.append(
                "Validate STR revenue assumptions with at least two independent sources."
            )
        else:
            checklist.append(
                "Confirm revenue quality: seasonality, fees, occupancy, and cleaning/management assumptions."
            )

    if hoa_monthly:
        checklist.append("Confirm exactly what HOA dues include and whether special assessments are pending.")

    if deal_tier == "UNREALISTIC":
        checklist.append(
            "Move on unless price, revenue, HOA, taxes, or insurance assumptions are materially wrong."
        )
    elif dscr < 1.00 or monthly_net < 0 or core_irr is None or core_irr < 0.08:
        checklist.append(
            "Use the solver before offering; the deal still misses at least one baseline target."
        )
    else:
        checklist.append(
            "If diligence confirms the assumptions, this can move into offer terms and negotiation posture."
        )

    return checklist


def build_risk_flags(
    deal_tier,
    results,
    ask_price,
    offer_price,
    annual_revenue,
    hoa_monthly,
    taxes_insurance_monthly,
):
    flags = []
    revenue_gap_pct = results.get("revenue_gap_pct")
    monthly_net = results.get("monthly_net", 0)
    dscr = results.get("dscr", 0)
    core_irr = results.get("core_five_year_irr")
    monthly_revenue = annual_revenue / 12 if annual_revenue else 0

    if deal_tier == "UNREALISTIC":
        flags.append(
            {
                "level": "high",
                "title": "Unrealistic deal",
                "detail": "Baseline targets are too far away. Move on unless a core assumption is wrong.",
            }
        )

    if monthly_net < 0:
        flags.append(
            {
                "level": "high",
                "title": "Negative monthly net",
                "detail": f"Current underwriting is short by {dollars_month(abs(monthly_net))}.",
            }
        )

    if dscr < 1.00:
        flags.append(
            {
                "level": "high" if dscr < 0.70 else "medium",
                "title": "DSCR below target",
                "detail": f"DSCR is {dscr:.2f}; debt coverage needs improvement before offer confidence is high.",
            }
        )

    if core_irr is None or core_irr < 0:
        flags.append(
            {
                "level": "high",
                "title": "Core return risk",
                "detail": "Core 5-year IRR is negative or unavailable before tax strategy.",
            }
        )
    elif core_irr < 0.08:
        flags.append(
            {
                "level": "medium",
                "title": "Weak core IRR",
                "detail": f"Core 5-year IRR is {pct(core_irr)}, below the 8.0% baseline.",
            }
        )

    if revenue_gap_pct is not None:
        if revenue_gap_pct > 0.30:
            flags.append(
                {
                    "level": "high",
                    "title": "Low revenue confidence",
                    "detail": f"Revenue needed is {revenue_gap_pct:.1%} above current assumptions; upside needs strong proof.",
                }
            )
        elif revenue_gap_pct >= 0.15:
            flags.append(
                {
                    "level": "medium",
                    "title": "Medium revenue confidence",
                    "detail": f"Revenue needed is {revenue_gap_pct:.1%} above current assumptions; validate before offering.",
                }
            )

    if annual_revenue and annual_revenue > 0:
        low_value = annual_revenue / 0.10
        high_value = annual_revenue / 0.07
        if offer_price > high_value:
            flags.append(
                {
                    "level": "high",
                    "title": "Overpaying risk",
                    "detail": f"Offer is above the implied value range of {dollars(low_value)} to {dollars(high_value)}.",
                }
            )
        elif offer_price > (low_value + (high_value - low_value) * 0.75):
            flags.append(
                {
                    "level": "medium",
                    "title": "Thin offer cushion",
                    "detail": "Offer is near the top of the revenue-implied value range.",
                }
            )

    if ask_price and offer_price >= ask_price * 0.98 and (dscr < 1.00 or monthly_net < 0):
        flags.append(
            {
                "level": "medium",
                "title": "Little negotiation cushion",
                "detail": "Current offer is close to ask while the deal still misses baseline targets.",
            }
        )

    if monthly_revenue:
        if hoa_monthly / monthly_revenue > 0.25:
            flags.append(
                {
                    "level": "medium",
                    "title": "High HOA burden",
                    "detail": "HOA is more than 25% of monthly revenue.",
                }
            )
        if taxes_insurance_monthly / monthly_revenue > 0.20:
            flags.append(
                {
                    "level": "medium",
                    "title": "High taxes / insurance burden",
                    "detail": "Taxes and insurance are more than 20% of monthly revenue.",
                }
            )

    return flags


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
    "property_state": "",
    "property_tax_rate_pct_input": 1.00,
    "insurance_rate_pct_input": 0.35,
    "utilities_monthly": 0,
    "str_profile": "Cabin / Mountain STR",
    "str_profile_applied": "",
    "property_management_fee_pct_input": 20.0,
    "maintenance_capex_pct_input": 6.0,
    "cleaning_turnover_monthly": 250,
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

_selected_state = st.session_state.get("property_state", "")
if _selected_state and st.session_state.get("escrow_rates_state_applied") != _selected_state:
    _tax_default, _insurance_default = STATE_ESCROW_DEFAULTS.get(
        _selected_state,
        DEFAULT_ESCROW_RATES,
    )
    st.session_state["property_tax_rate_pct_input"] = _tax_default
    st.session_state["insurance_rate_pct_input"] = _insurance_default
    st.session_state["escrow_rates_state_applied"] = _selected_state

if st.session_state.get("pending_use_auto_escrow"):
    _auto_escrow_value = st.session_state.get("pending_auto_escrow_value", 0)
    st.session_state["taxes_insurance_monthly"] = round(_auto_escrow_value)
    st.session_state["taxes_insurance_manual_override"] = False
    st.session_state.pop("pending_use_auto_escrow", None)
    st.session_state.pop("pending_auto_escrow_value", None)

if st.session_state.get("pending_reset_profile_defaults"):
    apply_profile_defaults(st.session_state.get("str_profile", "Cabin / Mountain STR"))
    st.session_state.pop("pending_reset_profile_defaults", None)

_active_profile = st.session_state.get("str_profile", "Cabin / Mountain STR")
if _active_profile != "Manual" and st.session_state.get("str_profile_applied") != _active_profile:
    apply_profile_defaults(_active_profile)

# --- Pending start new deal (must run before any widgets with these keys are created) ---
if st.session_state.get("pending_start_new_deal"):
    _fresh_deal_values = {
        "listing_text_input": "",
        "listing_url": "",
        "property_address": "",
        "market_city": "",
        "ask_price": 0,
        "offer_price": 0,
        "bedrooms": 0.0,
        "bathrooms": 0.0,
        "square_feet": 0,
        "prior_year_annual_income": 0,
        "hoa_monthly": 0,
        "taxes_insurance_monthly": 0,
        "property_state": "",
        "property_tax_rate_pct_input": default_values["property_tax_rate_pct_input"],
        "insurance_rate_pct_input": default_values["insurance_rate_pct_input"],
        "str_profile": "Cabin / Mountain STR",
        "str_profile_applied": "",
        "property_management_fee_pct_input": 20.0,
        "maintenance_capex_pct_input": 6.0,
        "utilities_monthly": 550,
        "cleaning_turnover_monthly": 250,
        "target_dscr": default_values["target_dscr"],
        "down_payment_pct_input": default_values["down_payment_pct_input"],
        "interest_rate_input": default_values["interest_rate_input"],
        "loan_term_years": default_values["loan_term_years"],
        "closing_costs": default_values["closing_costs"],
        "case_scenario": "Base",
        "county_appraisal_value": 0,
        "land_allocation_pct_input": default_values["land_allocation_pct_input"],
        "annual_w2_income": default_values["annual_w2_income"],
        "five_year_asset_pct_input": default_values["five_year_asset_pct_input"],
        "seven_year_asset_pct_input": default_values["seven_year_asset_pct_input"],
        "fifteen_year_asset_pct_input": default_values["fifteen_year_asset_pct_input"],
        "twenty_seven_half_year_asset_pct_input": default_values["twenty_seven_half_year_asset_pct_input"],
        "annual_market_appreciation_input": default_values["annual_market_appreciation_input"],
        "annual_rent_appreciation_input": default_values["annual_rent_appreciation_input"],
        "cost_to_sell_pct_input": default_values["cost_to_sell_pct_input"],
        "depreciation_recapture_tax_rate_input": default_values["depreciation_recapture_tax_rate_input"],
        "market_comp_annual_revenue": None,
        "market_comp_sold_price": None,
        "market_comp_nightly_rate": None,
        "market_comp_occupancy_pct": None,
        "market_comp_notes": "",
        "deal_notes_input": "",
        "taxes_insurance_manual_override": False,
        "escrow_rates_state_applied": "",
    }
    for _k, _v in _fresh_deal_values.items():
        st.session_state[_k] = _v

    _transient_keys = [
        "last_analyzed_deal",
        "max_offer_result",
        "loaded_saved_at",
        "pending_apply_scenario",
        "pending_load_saved_deal",
        "_solver_tier_applied",
    ]
    for _key in _transient_keys:
        st.session_state.pop(_key, None)
    for _key in list(st.session_state.keys()):
        if _key.startswith("solver_"):
            st.session_state.pop(_key, None)

    st.session_state.pop("pending_start_new_deal", None)
    st.session_state["new_deal_message"] = "Fresh deal started."

# --- Pending scenario apply (must run before any widgets with these keys are created) ---
if "pending_apply_scenario" in st.session_state:
    _pending = st.session_state.pop("pending_apply_scenario")
    st.session_state["offer_price"] = _pending["offer_price"]
    st.session_state["prior_year_annual_income"] = _pending["prior_year_annual_income"]
    st.session_state["hoa_monthly"] = _pending["hoa_monthly"]
    st.session_state["taxes_insurance_monthly"] = _pending["taxes_insurance_monthly"]
    st.session_state.pop("last_analyzed_deal", None)
    st.session_state.pop("solver_results", None)
    st.session_state.pop("max_offer_result", None)
    st.info("Scenario applied. Review updated inputs, then tap Analyze Deal.")

# --- Pending saved deal load (must run before any widgets with these keys are created) ---
if "pending_load_saved_deal" in st.session_state:
    _pending = st.session_state.pop("pending_load_saved_deal")
    for _key, _value in _pending.get("values", {}).items():
        st.session_state[_key] = _value
    st.session_state["loaded_saved_at"] = _pending.get("saved_at", "")
    st.session_state.pop("last_analyzed_deal", None)
    st.session_state.pop("solver_results", None)
    st.session_state.pop("max_offer_result", None)
    st.info("Saved deal loaded. Review inputs, then tap Analyze Deal.")

if "new_deal_message" in st.session_state:
    st.success(st.session_state.pop("new_deal_message"))

listing_text = st.text_area(
    "Paste Zillow URL or listing text",
    placeholder="Paste Zillow URL or listing details here. For now, listing text works best.\n\nExample:\n$725,000\n2 bed\n2 bath\n1,204 sqft\n$675 monthly HOA\n732 Scenic Gulf Dr #D301, Miramar Beach, FL 32550",
    height=120,
    key="listing_text_input",
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
    if st.button("Start Fresh Deal", use_container_width=True):
        st.session_state["pending_start_new_deal"] = True
        st.rerun()

st.divider()

use_auto_escrow = False

section_header("Assumption Profile", "Starting operating assumptions for STR underwriting.")
muted_text(
    "These are starting assumptions only. They help avoid underestimating STR operating costs. You can override them if you have actuals."
)
str_profile = st.selectbox(
    "Property / STR Profile",
    STR_PROFILE_OPTIONS,
    index=STR_PROFILE_OPTIONS.index(st.session_state.get("str_profile", "Cabin / Mountain STR"))
    if st.session_state.get("str_profile", "Cabin / Mountain STR") in STR_PROFILE_OPTIONS
    else 0,
    key="str_profile",
)
if str_profile != "Manual" and st.session_state.get("str_profile_applied") != str_profile:
    st.rerun()

with st.form("property_form"):
    section_header("Quick Deal Inputs")
    muted_text(
        "The key deal drivers. Ask price, HOA, and taxes can load from listing text; revenue usually needs Zillow, AirDNA, Rabbu, actuals, or owner data."
    )

    ask_price = currency_input(
        "Ask Price ($)",
        key="ask_price",
        help="Enter the listing price in dollars. Example: 615000.",
        blank_zero=True,
    )
    offer_price = currency_input(
        "Offer Price ($)",
        key="offer_price",
        help="Enter your proposed purchase price in dollars. Example: 585000.",
        blank_zero=True,
    )
    prior_year_annual_income = currency_input(
        "Estimated / Prior Year Annual Revenue ($)",
        key="prior_year_annual_income",
        help="Top-line annual rent or booking revenue before expenses. Example: 78000.",
        blank_zero=True,
    )
    hoa_monthly = currency_input(
        "HOA ($/mo)",
        key="hoa_monthly",
        help="Monthly HOA dues in dollars. Example: 850.",
        blank_zero=True,
    )

    escrow_col1, escrow_col2, escrow_col3 = st.columns(3)
    with escrow_col1:
        _state_index = (
            PROPERTY_STATE_OPTIONS.index(st.session_state.get("property_state", ""))
            if st.session_state.get("property_state", "") in PROPERTY_STATE_OPTIONS
            else 0
        )
        property_state = st.selectbox(
            "Property State",
            options=PROPERTY_STATE_OPTIONS,
            index=_state_index,
            format_func=lambda value: "Select state" if value == "" else value,
            key="property_state",
            help="Optional. Selecting a state applies rough tax and insurance rate defaults.",
        )
    with escrow_col2:
        property_tax_rate_pct_input = st.number_input(
            "Property Tax Rate %",
            step=0.05,
            key="property_tax_rate_pct_input",
            help="Rough annual property tax rate as a percent of purchase price. You can edit this estimate.",
        )
    with escrow_col3:
        insurance_rate_pct_input = st.number_input(
            "Insurance Rate %",
            step=0.05,
            key="insurance_rate_pct_input",
            help="Rough annual insurance rate as a percent of purchase price. You can edit this estimate.",
        )
    if property_state and st.session_state.get("escrow_rates_state_applied") != property_state:
        property_tax_rate_pct_input, insurance_rate_pct_input = STATE_ESCROW_DEFAULTS.get(
            property_state,
            DEFAULT_ESCROW_RATES,
        )

    _escrow_purchase_price = offer_price or ask_price
    _estimated_taxes_insurance = estimate_monthly_taxes_insurance(
        _escrow_purchase_price,
        property_tax_rate_pct_input,
        insurance_rate_pct_input,
    )
    _auto_escrow_rounded = round(_estimated_taxes_insurance) if _estimated_taxes_insurance else 0
    _escrow_manual_override = st.session_state.get("taxes_insurance_manual_override", False)
    if _auto_escrow_rounded and not _escrow_manual_override:
        st.session_state["taxes_insurance_monthly"] = round(_estimated_taxes_insurance)

    taxes_insurance_monthly = currency_input(
        "Taxes / Insurance ($/mo)",
        key="taxes_insurance_monthly",
        help="Auto-estimate uses purchase price x tax/insurance rates divided by 12. You can manually override this field.",
        blank_zero=True,
    )
    if _auto_escrow_rounded and abs((taxes_insurance_monthly or 0) - _auto_escrow_rounded) > 1:
        st.session_state["taxes_insurance_manual_override"] = True
        _escrow_manual_override = True

    if _auto_escrow_rounded:
        muted_text(
            f"Auto estimate: {dollars_month(_estimated_taxes_insurance)} using rough {property_state or 'state fallback'} assumptions ({property_tax_rate_pct_input:.2f}% tax, {insurance_rate_pct_input:.2f}% insurance)."
        )
        if _escrow_manual_override:
            muted_text(
                f"Manual override active. Auto estimate is {dollars_month(_estimated_taxes_insurance)}."
            )
            use_auto_escrow = st.form_submit_button(
                "Use Auto Estimate",
                use_container_width=True,
                on_click=normalize_currency_input_displays,
            )

    with st.expander("Property Details", expanded=False):
        muted_text("Loads automatically from listing text where available.")
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            property_address = st.text_input("Property Address", key="property_address")
            market_city = st.text_input("Market / City", key="market_city")
            bedrooms = st.number_input("Bedrooms", step=0.5, key="bedrooms")
        with pcol2:
            bathrooms = st.number_input("Bathrooms", step=0.5, key="bathrooms")
            square_feet = st.number_input("Square Feet", step=50, key="square_feet")

    with st.expander("Advanced Operating Assumptions", expanded=False):
        muted_text(
            "Profile defaults are editable. The current calculator directly uses the utilities line; management, reserve, and cleaning assumptions are shown for disciplined STR review."
        )
        acol1, acol2 = st.columns(2)
        with acol1:
            property_management_fee_pct_input = st.number_input(
                "Property Management Fee %",
                step=0.5,
                key="property_management_fee_pct_input",
            )
            maintenance_capex_pct_input = st.number_input(
                "Maintenance / CapEx Reserve %",
                step=0.5,
                key="maintenance_capex_pct_input",
            )
        with acol2:
            utilities_monthly = currency_input(
                "Utilities / Internet / Supplies ($/mo)",
                key="utilities_monthly",
                help="Monthly utility, internet, and supplies estimate in dollars.",
                blank_zero=True,
            )
            cleaning_turnover_monthly = currency_input(
                "Cleaning / Turnover Allowance ($/mo)",
                key="cleaning_turnover_monthly",
                help="Monthly allowance for cleaning or turnover costs if not already embedded in revenue or owner statements.",
                blank_zero=True,
            )
        if str_profile != "Manual":
            if st.form_submit_button("Reset to Profile Defaults", use_container_width=True):
                st.session_state["pending_reset_profile_defaults"] = True
                st.rerun()

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
            closing_costs = currency_input(
                "Closing Costs ($)",
                key="closing_costs",
                help="Estimated buyer closing costs in dollars. Example: 12000.",
                blank_zero=True,
            )
            target_dscr = st.number_input("Target DSCR", step=0.05, key="target_dscr")

    with st.expander("Tax Strategy", expanded=False):
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            county_appraisal_value = currency_input(
                "County Appraisal Value ($)",
                key="county_appraisal_value",
                help="County appraisal value in dollars. Example: 430000.",
                blank_zero=True,
            )
            land_allocation_pct_input = st.number_input(
                "Land Allocation %", step=1.0, key="land_allocation_pct_input"
            )
            annual_w2_income = currency_input(
                "Annual W-2 Income ($)",
                key="annual_w2_income",
                help="Annual W-2 income in dollars for tax strategy modeling. Example: 354000.",
                blank_zero=True,
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
                "Model Scenario",
                ["Aggressive", "Base", "Conservative"],
                index=["Aggressive", "Base", "Conservative"].index(
                    st.session_state["case_scenario"]
                ),
                key="case_scenario",
                help="Global model setting for revenue haircut, STR costs, and maintenance. This is not just an exit assumption.",
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

    submitted = st.form_submit_button(
        "Analyze Deal",
        use_container_width=True,
        type="primary",
        on_click=normalize_currency_input_displays,
    )

if use_auto_escrow:
    st.session_state["pending_use_auto_escrow"] = True
    st.session_state["pending_auto_escrow_value"] = _auto_escrow_rounded
    st.rerun()

if property_state and st.session_state.get("escrow_rates_state_applied") != property_state:
    st.rerun()


with st.expander("Developer / QA Runner", expanded=False):
    muted_text("Hidden testing utility for validating deal score, verdict, and risk behavior across predefined scenarios.")
    if st.button("Run Stress Test", use_container_width=True):
        _qa_rows = run_qa_scenarios()
        st.dataframe(pd.DataFrame(_qa_rows), use_container_width=True, hide_index=True)
        _flagged_rows = [row for row in _qa_rows if row["Flags"] != "OK"]
        if _flagged_rows:
            st.warning(
                f"{len(_flagged_rows)} QA scenario(s) returned flags. Review score/verdict alignment before shipping."
            )
        else:
            st.success("Stress test completed with no score/verdict flags.")

    st.divider()
    st.markdown("**Sensitivity Sweep Engine**")
    muted_text(
        "Stress test a single assumption across a range to identify score cliffs, unstable underwriting behavior, and verdict transition points."
    )

    _base_sweep_inputs = PropertyInputs(
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
    _base_comp_revenue = parse_currency_value(st.session_state.get("market_comp_annual_revenue"))
    _base_occupancy_pct = (
        st.session_state.get("market_comp_occupancy_pct")
        if st.session_state.get("market_comp_occupancy_pct")
        else 60.0
    )
    _base_nightly_rate = (
        parse_currency_value(st.session_state.get("market_comp_nightly_rate"))
        or (
            prior_year_annual_income / (365 * (_base_occupancy_pct / 100))
            if prior_year_annual_income and _base_occupancy_pct
            else 0
        )
    )

    _sweep_variable = st.selectbox(
        "Sweep Variable",
        [
            "Annual Revenue",
            "Offer Price",
            "Interest Rate",
            "Occupancy",
            "Nightly Rate",
            "Exit Cap Rate",
            "Property Tax Rate",
        ],
        key="sweep_variable",
    )
    _sweep_start_default, _sweep_end_default = sensitivity_default_range(
        _sweep_variable,
        _base_sweep_inputs,
        _base_occupancy_pct,
        _base_nightly_rate,
        property_tax_rate_pct_input,
    )
    _sweep_key = re.sub(r"[^a-z0-9]+", "_", _sweep_variable.lower()).strip("_")
    _sw1, _sw2, _sw3 = st.columns(3)
    with _sw1:
        _sweep_start = st.number_input(
            "Start Value",
            value=float(_sweep_start_default),
            key=f"sweep_start_{_sweep_key}",
        )
    with _sw2:
        _sweep_end = st.number_input(
            "End Value",
            value=float(_sweep_end_default),
            key=f"sweep_end_{_sweep_key}",
        )
    with _sw3:
        _sweep_steps = st.number_input(
            "Step Count",
            min_value=2,
            max_value=100,
            value=20,
            step=1,
            key="sweep_step_count",
        )

    if st.button("Run Sensitivity Sweep", use_container_width=True):
        _sweep_rows = run_sensitivity_sweep(
            _base_sweep_inputs,
            _sweep_variable,
            _sweep_start,
            _sweep_end,
            int(_sweep_steps),
            comp_revenue=_base_comp_revenue,
            base_occupancy_pct=_base_occupancy_pct,
            base_nightly_rate=_base_nightly_rate,
            insurance_rate_pct=insurance_rate_pct_input,
        )
        _sweep_df = pd.DataFrame(_sweep_rows)
        _display_cols = [
            "Sweep Value",
            "Score",
            "DSCR",
            "Core IRR",
            "Monthly Net",
            "Revenue Needed",
            "Verdict",
            "Revenue Premium",
            "Flags",
        ]
        st.dataframe(_sweep_df[_display_cols], use_container_width=True, hide_index=True)

        _chart_df = _sweep_df[
            ["Sweep Raw", "Score", "DSCR Raw", "Monthly Net Raw"]
        ].rename(
            columns={
                "Sweep Raw": "Sweep Value",
                "DSCR Raw": "DSCR",
                "Monthly Net Raw": "Monthly Net",
            }
        )
        _chart_df = _chart_df.set_index("Sweep Value")
        _ch1, _ch2, _ch3 = st.columns(3)
        with _ch1:
            st.caption("Score vs Sweep Variable")
            st.line_chart(_chart_df[["Score"]])
        with _ch2:
            st.caption("DSCR vs Sweep Variable")
            st.line_chart(_chart_df[["DSCR"]])
        with _ch3:
            st.caption("Monthly Net vs Sweep Variable")
            st.line_chart(_chart_df[["Monthly Net"]])

        info_card(
            "Sweep Insights",
            " ".join(sensitivity_insights(_sweep_rows, _sweep_variable)),
        )


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
    if any(_key.endswith("_needs_currency_format") for _key in st.session_state.keys()):
        st.rerun()


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

    # --- Deal Quality Tier ---
    _tier_dscr = results["dscr"]
    _tier_net = results["monthly_net"]
    _tier_irr = results.get("core_five_year_irr")
    _tier_gap_pct = results.get("revenue_gap_pct", 0) or 0

    if (_tier_dscr >= 1.00 and _tier_net >= 0
            and _tier_irr is not None and _tier_irr >= 0.08):
        _deal_tier = "STRONG"
        _expander_title = "How Could This Deal Become Excellent?"
        _tier_dscr_default = 1.20
        _tier_net_default = 500
        _tier_irr_default = 15.0
    elif (_tier_gap_pct <= 0.30 or _tier_dscr >= 0.70
          or (_tier_irr is not None and _tier_irr >= 0.0)):
        _deal_tier = "FIXABLE"
        _expander_title = "What Would Make This Deal Work?"
        _tier_dscr_default = 1.00
        _tier_net_default = 0
        _tier_irr_default = 8.0
    else:
        _deal_tier = "UNREALISTIC"
        _expander_title = "What Would Make This Deal Work?"
        _tier_dscr_default = 1.00
        _tier_net_default = 0
        _tier_irr_default = 8.0

    _revenue_display = revenue_gap_display(results)
    _score_comp_revenue = parse_currency_value(
        st.session_state.get("market_comp_annual_revenue")
    )
    _score_revenue_delta_pct = (
        (_prior_year_annual_income - _score_comp_revenue) / _score_comp_revenue
        if _score_comp_revenue
        else None
    )
    _score_revenue_realism_label = None
    if _score_revenue_delta_pct is not None:
        _score_revenue_realism_label, _ = market_reality_label(
            _score_revenue_delta_pct,
            "Revenue",
        )
    _score_offer_position = offer_position_label(
        _offer_price,
        _prior_year_annual_income,
    )
    _deal_score = calculate_deal_score(
        dscr=results.get("dscr"),
        monthly_net=results.get("monthly_net"),
        core_irr=results.get("core_five_year_irr"),
        revenue_gap=results.get("revenue_gap_dollars"),
        annual_revenue=_prior_year_annual_income,
        revenue_realism_label=_score_revenue_realism_label,
        revenue_premium_pct=_score_revenue_delta_pct,
        offer_position=_score_offer_position,
    )
    _deal_score_label = deal_score_label(_deal_score)
    verdict_label = display_verdict_label(
        verdict.get("verdict", "REVIEW"),
        _score_revenue_delta_pct,
    )

    section_header("Deal Decision", "Read this first, then inspect the risks and offer path.")

    if _score_revenue_delta_pct is not None and _score_revenue_delta_pct > 0.35:
        status_badge("SPECULATIVE", "danger")
        summary = "Aggressive assumptions: revenue is materially above nearby comp support. Verify revenue proof before treating this as offer-ready."
    elif _deal_tier == "STRONG":
        status_badge("STRONG DEAL", "success")
        summary = "This clears baseline targets. Verify assumptions, then consider offer strategy."
    elif _deal_tier == "FIXABLE":
        status_badge("CLOSE / FIXABLE", "warning")
        summary = "This may work, but only if the gap can be solved through realistic changes."
    else:
        status_badge("UNREALISTIC", "danger")
        summary = "Move on unless a major price, revenue, or expense assumption is wrong."

    muted_text(summary)

    section_header("Deal Snapshot", "Core underwriting outputs for offer confidence.")
    deal_score_card(
        _deal_score,
        _deal_score_label,
        deal_score_explanation(
            _deal_score_label,
            _score_revenue_realism_label,
            _score_offer_position,
        ),
    )

    ds1, ds2 = st.columns(2)
    ds1.metric("Monthly Net", dollars_month(results["monthly_net"]))
    ds2.metric("DSCR", f"{results['dscr']:.2f}")

    ds3, ds4 = st.columns(2)
    ds3.metric(
        "Core 5-Year IRR",
        pct(results["core_five_year_irr"]) if results["core_five_year_irr"] is not None else "N/A",
    )
    ds4.metric(_revenue_display["label"], _revenue_display["value"])

    ds5, _ = st.columns(2)
    ds5.metric(
        "Tax-Enhanced IRR",
        pct(results["five_year_irr"]) if results["five_year_irr"] is not None else "N/A",
    )
    status_badge(_revenue_display["label"], _revenue_display["status"])
    muted_text(_revenue_display["text"])

    st.markdown("**Metric Explainers**")
    metric_explainer(
        "Monthly Net",
        "Estimated monthly cash flow after mortgage, HOA, taxes, insurance, utilities, and operating costs.",
        "It shows whether the property is likely to help or hurt monthly household cash flow.",
        "$0+/mo is baseline; $500+/mo is stronger.",
    )
    metric_explainer(
        "DSCR",
        "Debt service coverage ratio: revenue available to cover loan payments after operating expenses.",
        "Lenders and investors use it to judge whether the deal can safely support its debt.",
        "1.00x+ covers debt; 1.20x+ gives more cushion.",
    )
    metric_explainer(
        "Core 5-Year IRR",
        "Estimated five-year return before tax strategy benefits.",
        "It helps separate the actual deal quality from tax-driven upside.",
        "8%+ is acceptable; 15%+ is strong.",
    )
    metric_explainer(
        "Revenue Needed / Cushion",
        "Revenue Needed means the deal still needs more annual revenue. Revenue Cushion means current assumptions already exceed the target.",
        "It shows whether revenue is a problem to solve or a cushion to verify.",
        "$0 needed or a positive cushion is better.",
    )

    st.markdown("**Before You Offer**")
    _before_offer_items = build_before_offer_checklist(
        _deal_tier,
        results,
        _offer_price,
        _prior_year_annual_income,
        _hoa_monthly,
    )
    for _item in _before_offer_items:
        st.markdown(f"- [ ] {_item}")

    st.markdown("**Risk Flags**")
    _risk_flags = build_risk_flags(
        _deal_tier,
        results,
        _ask_price,
        _offer_price,
        _prior_year_annual_income,
        _hoa_monthly,
        _taxes_insurance_monthly,
    )
    if _risk_flags:
        for _flag in _risk_flags:
            _message = f"**{_flag['title']}** - {_flag['detail']}"
            if _flag["level"] == "high":
                st.error(_message)
            elif _flag["level"] == "medium":
                st.warning(_message)
            else:
                st.info(_message)
    else:
        st.success("No major underwriting risk flags from the current inputs.")

    if st.session_state.get("_solver_tier_applied") != _deal_tier:
        st.session_state["solver_tgt_dscr"] = _tier_dscr_default
        st.session_state["solver_tgt_monthly_net"] = float(_tier_net_default)
        st.session_state["solver_tgt_core_irr"] = _tier_irr_default
        st.session_state["_solver_tier_applied"] = _deal_tier

    st.session_state["last_analyzed_deal"]["deal_quality"] = _deal_tier

    with st.expander(_expander_title, expanded=False):
        _breakeven = results.get("breakeven_revenue", 0)
        _current_rev = results.get("average_monthly_revenue", 0) * 12
        _gap_dollars = results["revenue_gap_dollars"]
        _gap_pct = results.get("revenue_gap_pct", 0)

        bm1, bm2 = st.columns(2)
        bm1.metric("Required Annual Revenue", dollars(_breakeven))
        bm2.metric("Current Annual Revenue", dollars(_current_rev))

        _solver_revenue_display = revenue_gap_display(results)
        bm3, bm4 = st.columns(2)
        bm3.metric(_solver_revenue_display["label"], _solver_revenue_display["value"])
        bm4.metric("Revenue Need %", f"{max(_gap_pct, 0):.1%}" if _gap_pct is not None else "N/A")

        if _gap_dollars <= 0:
            st.success("Revenue already clears the target DSCR. Verify the source before relying on it.")
        elif _gap_pct <= 0.10:
            st.info("Small gap. This may be fixable with modestly better revenue or expenses.")
        elif _gap_pct <= 0.25:
            st.warning("Medium gap. The deal likely needs a lower offer price or stronger revenue proof.")
        else:
            st.error("Large gap. Move on unless revenue assumptions materially improve.")

        if _deal_tier == "UNREALISTIC":
            st.divider()
            st.error(
                "This deal is too far from your baseline targets. "
                "Do not spend time optimizing unless the revenue, price, or expense assumptions are materially wrong."
            )
        else:
            if _deal_tier == "STRONG":
                st.info(
                    "This deal already clears your baseline. "
                    "These scenarios show what would make it excellent."
                )

            st.divider()
            st.markdown("**Investor Targets**")

            _tc1, _tc2 = st.columns(2)
            with _tc1:
                _tgt_dscr = st.number_input("Target DSCR", step=0.05, key="solver_tgt_dscr")
                _tgt_monthly_net = currency_input(
                    "Min Monthly Net ($)",
                    key="solver_tgt_monthly_net",
                    help="Minimum monthly net cash flow target in dollars. Example: 500.",
                    blank_zero=True,
                )
                _tgt_core_irr = st.number_input("Min Core 5-Yr IRR %", step=0.5, key="solver_tgt_core_irr")
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

            st.markdown("**Max Offer Price**")
            if st.button("Find Max Offer", use_container_width=True, key="find_max_offer_btn"):
                _max_offer_result = None
                _max_offer_start = int(_ask_price)
                _max_offer_floor = int(_ask_price * 0.70)
                _max_offer_vals = list(range(_max_offer_start, _max_offer_floor - 1, -5000))
                if _max_offer_floor not in _max_offer_vals:
                    _max_offer_vals.append(_max_offer_floor)

                for _test_offer in _max_offer_vals:
                    _test_results = calculate(
                        PropertyInputs(
                            **{
                                **_base_kwargs,
                                "offer_price": _test_offer,
                            }
                        )
                    )
                    if _meets_targets(_test_results):
                        _max_offer_result = {
                            "offer_price": _test_offer,
                            "prior_year_annual_income": _prior_year_annual_income,
                            "hoa_monthly": _hoa_monthly,
                            "taxes_insurance_monthly": _taxes_insurance_monthly,
                            "monthly_net": _test_results["monthly_net"],
                            "dscr": _test_results["dscr"],
                            "core_five_year_irr": _test_results["core_five_year_irr"],
                            "coc": _test_results.get("coc"),
                            "equity_multiple": _test_results.get("equity_multiple"),
                        }
                        break

                st.session_state["max_offer_result"] = _max_offer_result

            _max_offer_result = st.session_state.get("max_offer_result")
            if _max_offer_result:
                _max_delta = _max_offer_result["offer_price"] - _offer_price
                st.success(f"Max offer that hits selected targets: {dollars(_max_offer_result['offer_price'])}")
                _mo1, _mo2 = st.columns(2)
                _mo1.metric("Room vs Current Offer", dollars(_max_delta))
                _mo2.metric("DSCR", f"{_max_offer_result['dscr']:.2f}")
                _mo3, _mo4 = st.columns(2)
                _mo3.metric(
                    "Monthly Net",
                    dollars_month(_max_offer_result["monthly_net"]),
                )
                _mo4.metric(
                    "Core IRR",
                    pct(_max_offer_result["core_five_year_irr"])
                    if _max_offer_result["core_five_year_irr"] is not None
                    else "N/A",
                )

                if st.button("Apply Max Offer", use_container_width=True, key="apply_max_offer_btn"):
                    st.session_state["pending_apply_scenario"] = {
                        "offer_price": float(_max_offer_result["offer_price"]),
                        "prior_year_annual_income": float(_max_offer_result["prior_year_annual_income"]),
                        "hoa_monthly": float(_max_offer_result["hoa_monthly"]),
                        "taxes_insurance_monthly": float(_max_offer_result["taxes_insurance_monthly"]),
                    }
                    st.rerun()
            elif _max_offer_result is None and "max_offer_result" in st.session_state:
                st.error("No offer price from ask down to 70% of ask hits the selected targets.")

        if _deal_tier != "UNREALISTIC" and st.button("Run Deal Solver", use_container_width=True, type="primary", key="run_solver_btn"):
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
                                _price_chg_pct = (_offer_price - _op) / _offer_price if _offer_price else 0
                                _rev_chg_pct = (_rv - _prior_year_annual_income) / _prior_year_annual_income if _prior_year_annual_income else 0
                                _lever_count = sum(
                                    [
                                        _op != _offer_price,
                                        _rv != _prior_year_annual_income,
                                        _hoa != _hoa_monthly,
                                        _tx != _taxes_insurance_monthly,
                                    ]
                                )
                                _heavy_lift = _price_chg_pct > 0.20 or _rev_chg_pct > 0.30
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
                                    "_lever_count": _lever_count,
                                    "_heavy_lift": _heavy_lift,
                                    "_delta": _delta,
                                })

            if not _found:
                st.session_state["solver_results"] = []
                st.session_state["solver_no_result_gap"] = {
                    "current_rev": results.get("average_monthly_revenue", 0) * 12,
                    "breakeven_rev": results.get("breakeven_revenue", 0),
                    "gap_dollars": results.get("revenue_gap_dollars", 0),
                    "gap_pct": results.get("revenue_gap_pct", 0),
                }
            else:
                _found.sort(
                    key=lambda x: (
                        x["_heavy_lift"],
                        max(x["_lever_count"], 1),
                        x["_delta"],
                    )
                )
                st.session_state["solver_results"] = _found[:5]
                st.session_state["solver_base_offer"] = _offer_price
                st.session_state["solver_base_revenue"] = _prior_year_annual_income
                st.session_state["solver_base_hoa"] = _hoa_monthly
                st.session_state["solver_base_tax"] = _taxes_insurance_monthly

        _solver_top5 = (
            st.session_state.get("solver_results")
            if _deal_tier != "UNREALISTIC"
            else None
        )

        if _solver_top5 is not None:
            if not _solver_top5:
                st.error("No realistic scenario found within the selected limits.")
                _no_gap = st.session_state.get("solver_no_result_gap", {})
                _ng_current = _no_gap.get("current_rev", 0)
                _ng_breakeven = _no_gap.get("breakeven_rev", 0)
                _ng_gap_dollars = _no_gap.get("gap_dollars", 0)
                _ng_gap_pct = _no_gap.get("gap_pct", 0)
                if _ng_current or _ng_breakeven:
                    _ng_display = revenue_gap_display(
                        {"revenue_gap_dollars": _ng_gap_dollars}
                    )
                    _ng1, _ng2 = st.columns(2)
                    _ng1.metric("Current Annual Revenue", dollars(_ng_current))
                    _ng2.metric("Required Annual Revenue", dollars(_ng_breakeven))
                    _ng3, _ng4 = st.columns(2)
                    _ng3.metric(_ng_display["label"], _ng_display["value"])
                    _ng4.metric("Revenue Need %", f"{max(_ng_gap_pct, 0):.1%}" if _ng_gap_pct is not None else "N/A")
                if _ng_gap_pct is not None and _ng_gap_pct > 0.50:
                    st.warning("Recommendation: Move on unless you have strong proof that revenue can materially outperform the current estimate.")
                elif _ng_gap_pct is not None and _ng_gap_pct > 0.25:
                    st.warning("Recommendation: This is a heavy lift. Only continue if price, revenue, or expenses can change materially.")
                else:
                    st.info("Recommendation: Try adding another lever or slightly loosening investor targets.")

                if "Lower Offer Price" in _levers and "Increase Annual Revenue" not in _levers:
                    st.caption("Deal Driver Insight: Lowering the price alone does not appear to solve this deal within your selected limits.")
            else:
                _sb_offer = st.session_state.get("solver_base_offer", _offer_price)
                _sb_rev = st.session_state.get("solver_base_revenue", _prior_year_annual_income)
                _sb_hoa = st.session_state.get("solver_base_hoa", _hoa_monthly)
                _sb_tax = st.session_state.get("solver_base_tax", _taxes_insurance_monthly)

                # --- Deal Driver Insight ---
                _s1 = _solver_top5[0]
                _s1_price_dropped = _s1["offer_price"] < _sb_offer
                _s1_rev_increased = _s1["prior_year_annual_income"] > _sb_rev
                _both_levers = "Lower Offer Price" in _levers and "Increase Annual Revenue" in _levers
                _rev_only = "Increase Annual Revenue" in _levers and "Lower Offer Price" not in _levers

                if _both_levers:
                    if _s1_price_dropped and _s1_rev_increased:
                        _insight = "Deal Driver Insight: This is a dual-lever deal. It likely needs both a better purchase price and stronger revenue to hit your targets."
                    elif _s1_rev_increased:
                        _insight = "Deal Driver Insight: This is primarily a revenue-driven deal. Better revenue performance is doing most of the work."
                    else:
                        _insight = "Deal Driver Insight: This is primarily a price-driven deal. The deal works mainly by buying it at a lower basis."
                    st.caption(_insight)
                elif _rev_only:
                    st.caption("Deal Driver Insight: Revenue alone can make this deal work, but validate the revenue assumption carefully.")

                for _i, _s in enumerate(_solver_top5, 1):
                    _price_chg_pct = (_sb_offer - _s["offer_price"]) / _sb_offer if _sb_offer else 0
                    _rev_chg_pct = (_s["prior_year_annual_income"] - _sb_rev) / _sb_rev if _sb_rev else 0

                    if _price_chg_pct <= 0.10 and _rev_chg_pct <= 0.15:
                        _realism = "High"
                        _effort = "Easy Fix"
                    elif _price_chg_pct <= 0.20 and _rev_chg_pct <= 0.30:
                        _realism = "Medium"
                        _effort = "Moderate Fix"
                    else:
                        _realism = "Low"
                        _effort = "Heavy Lift"

                    _header = f"**Scenario #{_i}**" + (" - Top Pick" if _i == 1 else "")
                    st.markdown(_header)
                    st.caption(f"Offer: {dollars(_s['offer_price'])} | Revenue: {dollars(_s['prior_year_annual_income'])}")

                    _changes = []
                    _price_diff = _sb_offer - _s["offer_price"]
                    if _price_diff != 0:
                        _changes.append(f"Price: {dollars(_s['offer_price'])} (-{dollars(_price_diff)})")
                    _rev_diff = _s["prior_year_annual_income"] - _sb_rev
                    if _rev_diff != 0:
                        _changes.append(f"Revenue: {dollars(_s['prior_year_annual_income'])} (+{dollars(_rev_diff)})")
                    _hoa_diff = _sb_hoa - _s["hoa_monthly"]
                    if _hoa_diff != 0:
                        _changes.append(f"HOA: {dollars(_s['hoa_monthly'])}/mo (-{dollars(_hoa_diff)})")
                    _tax_diff = _sb_tax - _s["taxes_insurance_monthly"]
                    if _tax_diff != 0:
                        _changes.append(f"Taxes/Ins: {dollars(_s['taxes_insurance_monthly'])}/mo (-{dollars(_tax_diff)})")

                    if _changes:
                        st.markdown("*What Changed:* " + " | ".join(_changes))

                    _mc1, _mc2 = st.columns(2)
                    _mc1.metric("Monthly Net", dollars(_s["monthly_net"]))
                    _mc2.metric("DSCR", f"{_s['dscr']:.2f}")
                    _mc3, _mc4 = st.columns(2)
                    _mc3.metric("Core IRR", pct(_s["core_five_year_irr"]) if _s["core_five_year_irr"] is not None else "N/A")
                    _mc4.metric("Cash-on-Cash", pct(_s["coc"]) if _s["coc"] is not None else "N/A")
                    _mc5, _mc6 = st.columns(2)
                    _mc5.metric("Eq. Multiple", f"{_s['equity_multiple']:.2f}" if _s["equity_multiple"] is not None else "N/A")
                    _mc6.metric("Realism", f"{_realism} | {_effort}")

                    _hard_lines = []
                    if _rev_chg_pct > 0.30:
                        _hard_lines.append("Requires a large increase in revenue relative to current assumptions.")
                    if _price_chg_pct > 0.20:
                        _hard_lines.append("Requires a significant price discount below current offer.")
                    if _hard_lines:
                        st.caption("Caution: " + " | ".join(_hard_lines))

                    _apply_s = _s
                    if st.button(f"Apply Scenario #{_i}", key=f"apply_scenario_{_i}", use_container_width=True):
                        st.session_state["pending_apply_scenario"] = {
                            "offer_price": float(_apply_s["offer_price"]),
                            "prior_year_annual_income": float(_apply_s["prior_year_annual_income"]),
                            "hoa_monthly": float(_apply_s["hoa_monthly"]),
                            "taxes_insurance_monthly": float(_apply_s["taxes_insurance_monthly"]),
                        }
                        st.rerun()

                    if _i < len(_solver_top5):
                        st.divider()

                with st.expander("Detailed Solver Table", expanded=False):
                    _rows = []
                    for _i, _s in enumerate(_solver_top5, 1):
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

    section_header(
        "Market Reality Check",
        "Manual comp pressure test for revenue and offer assumptions.",
    )
    _comp_col1, _comp_col2 = st.columns(2)
    with _comp_col1:
        _comp_revenue = currency_input(
            "Nearby Comp Annual Revenue ($)",
            key="market_comp_annual_revenue",
            help="Example: 78000",
            allow_none=True,
        )
        _comp_sold_price = currency_input(
            "Nearby Comp Sold Price ($)",
            key="market_comp_sold_price",
            help="Example: 600000",
            allow_none=True,
        )
    with _comp_col2:
        _comp_nightly_rate = currency_input(
            "Nearby Comp Nightly Rate ($)",
            key="market_comp_nightly_rate",
            help="Example: 475",
            allow_none=True,
        )
        _comp_occupancy_pct = st.number_input(
            "Nearby Comp Occupancy %",
            min_value=0.0,
            max_value=100.0,
            value=None,
            step=1.0,
            key="market_comp_occupancy_pct",
            help="Example: 62",
        )
    _comp_notes = st.text_area(
        "Notes / Source",
        placeholder="AirDNA, Rabbu, owner actuals, MLS sale, county records...",
        height=80,
        key="market_comp_notes",
    )

    _revenue_delta_pct = (
        (_prior_year_annual_income - _comp_revenue) / _comp_revenue
        if _comp_revenue
        else None
    )
    _price_delta_pct = (
        (_offer_price - _comp_sold_price) / _comp_sold_price
        if _comp_sold_price
        else None
    )
    _revenue_label, _revenue_status = market_reality_label(
        _revenue_delta_pct,
        "Revenue",
    )
    _offer_label, _offer_status = market_reality_label(
        _price_delta_pct,
        "Offer",
    )

    if _revenue_delta_pct is None and _price_delta_pct is None:
        info_card(
            "Reality Check",
            "Enter at least one nearby comp revenue or sold price to pressure-test the current assumptions.",
        )
    else:
        _mr1, _mr2 = st.columns(2)
        _mr1.metric(
            "Revenue Premium / Discount",
            f"{_revenue_delta_pct:+.1%}" if _revenue_delta_pct is not None else "No revenue comp",
        )
        _mr2.metric(
            "Price Premium / Discount",
            f"{_price_delta_pct:+.1%}" if _price_delta_pct is not None else "No price comp",
        )

        _rl, _ol = st.columns(2)
        with _rl:
            status_badge(_revenue_label, _revenue_status)
        with _ol:
            status_badge(_offer_label, _offer_status)

        info_card(
            "Reality Check",
            market_reality_interpretation(
                _revenue_delta_pct,
                _price_delta_pct,
            ),
        )

    if _comp_nightly_rate or _comp_occupancy_pct or _comp_notes:
        muted_text(
            "Use nightly rate, occupancy, and source notes to judge whether this comp is actually comparable."
        )

    section_header(
        "Verify Before Offer",
        "Fast research access only. Confirm county records manually before submitting an offer.",
    )

    _diligence_links = build_due_diligence_links(_property_address, _market_city)
    for _idx in range(0, len(_diligence_links), 2):
        _cols = st.columns(2)
        for _col, _item in zip(_cols, _diligence_links[_idx:_idx + 2]):
            with _col:
                st.link_button(_item["label"], _item["url"], use_container_width=True)
                muted_text(_item["note"])

    with st.expander("STR Regulation Lookup (later)", expanded=False):
        muted_text(
            "Future workflow: open city/county STR rules, permit requirements, zoning limits, "
            "occupancy rules, and HOA rental restrictions from one place."
        )

    _status_defaults = {
        "BUY": "Offer Ready",
        "REVIEW": "Analyzing",
        "DO NOT BUY": "Passed",
    }
    _status_options = PIPELINE_STATUSES
    _default_status = _status_defaults.get(verdict_label, "Analyzing")
    _default_status_idx = _status_options.index(_default_status) if _default_status in _status_options else 0

    deal_status = st.selectbox(
        "Deal Status",
        options=_status_options,
        index=_default_status_idx,
        key="deal_status_input",
    )

    pass_reason = ""
    if deal_status == "Passed":
        pass_reason = st.selectbox(
            "Why I Passed",
            options=PASS_REASONS,
            key="pass_reason_input",
        )

    deal_notes = st.text_area(
        "Deal Notes",
        placeholder="Location thoughts, inspection flags, seller motivation, comps...",
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
        "deal_quality": _deal_tier,
        "revenue_confidence": revenue_confidence_label(results.get("revenue_gap_pct")),
        "max_offer": (
            st.session_state.get("max_offer_result", {}).get("offer_price", "")
            if isinstance(st.session_state.get("max_offer_result"), dict)
            else ""
        ),
        "pass_reason": pass_reason,
        "verdict": verdict_label,
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
                st.write(f"Good: {strength}")

    if reasons:
        with st.expander("Concerns / Notes", expanded=True):
            for reason in reasons:
                st.write(f"Note: {reason}")

    st.divider()

    section_header("Property Snapshot")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Bedrooms", f"{_bedrooms:g}")
    p2.metric("Bathrooms", f"{_bathrooms:g}")
    p3.metric("Square Feet", f"{_square_feet:,.0f}")
    p4.metric(
        "Price / Sq Ft", dollars(_offer_price / _square_feet) if _square_feet else "N/A"
    )

    if _property_address:
        muted_text(f"Address: {_property_address}")

    st.divider()

    section_header("Investor Snapshot")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Offer Price", dollars(results["current_market_value"]))
    k2.metric("Down Payment", dollars(results["down_payment"]))
    k3.metric("Mortgage Balance", dollars(results["mortgage_balance"]))
    k4.metric("Seller Credits", dollars(results["seller_credits"]))

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Avg Monthly Revenue", dollars_month(results["average_monthly_revenue"]))
    k6.metric("Monthly Net", dollars_month(results["monthly_net"]))
    k7.metric("DSCR", f"{results['dscr']:.2f}")
    k8.metric(_revenue_display["label"], _revenue_display["value"])

    st.divider()

    section_header("Return Profile")

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

    section_header("Tax Strategy")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Depreciable Basis", dollars(results["depreciable_basis"]))
    t2.metric("Year-1 Depreciation", dollars(results["year_1_depreciation"]))
    t3.metric("Year-1 Tax Shield", dollars(results["year_1_tax_shield"]))
    t4.metric("Year 2+ Tax Shield", dollars(results["year_2_plus_tax_shield"]))

    st.divider()

    section_header("Cash Flow by Buydown Year")

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

    section_header("Scenario Comparison")

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
                "Revenue Needed": max(scenario_results["revenue_gap_dollars"], 0),
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
                "Revenue Needed": "${:,.0f}",
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
        _pipeline_view = saved.copy()
        _pipeline_view["deal_status"] = _pipeline_view["deal_status"].apply(normalize_pipeline_status)
        _pipeline_view["deal_quality"] = _pipeline_view["deal_quality"].apply(lambda v: safe_text(v, "Unknown"))
        _pipeline_view["revenue_confidence"] = _pipeline_view.apply(
            lambda row: safe_text(
                row.get("revenue_confidence"),
                revenue_confidence_label(row.get("revenue_gap_pct")),
            ),
            axis=1,
        )

        section_header("Acquisition Pipeline", "Saved opportunities by status, quality, and revenue confidence.")
        _filter_col1, _filter_col2, _filter_col3 = st.columns(3)
        with _filter_col1:
            _pipeline_status_filter = st.selectbox(
                "Deal Status",
                options=["All"] + PIPELINE_STATUSES,
                key="pipeline_status_filter",
            )
        with _filter_col2:
            _quality_options = ["All"] + sorted(
                [q for q in _pipeline_view["deal_quality"].dropna().unique().tolist() if q]
            )
            _pipeline_quality_filter = st.selectbox(
                "Deal Quality",
                options=_quality_options,
                key="pipeline_quality_filter",
            )
        with _filter_col3:
            _pipeline_confidence_filter = st.selectbox(
                "Revenue Confidence",
                options=["All", "High", "Medium", "Low", "Unknown"],
                key="pipeline_confidence_filter",
            )

        _cards = _pipeline_view.copy()
        if _pipeline_status_filter != "All":
            _cards = _cards[_cards["deal_status"] == _pipeline_status_filter]
        if _pipeline_quality_filter != "All":
            _cards = _cards[_cards["deal_quality"] == _pipeline_quality_filter]
        if _pipeline_confidence_filter != "All":
            _cards = _cards[_cards["revenue_confidence"] == _pipeline_confidence_filter]

        if _cards.empty:
            muted_text("No saved deals match these filters.")
        else:
            muted_text(f"{len(_cards)} saved deal{'s' if len(_cards) != 1 else ''} in this view.")

            def _pending_values_from_saved_row(row):
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
                    "ask_price": "ask_price",
                    "offer_price": "offer_price",
                }
                _numeric = {
                    "bedrooms", "bathrooms", "square_feet", "prior_year_annual_income",
                    "hoa_monthly", "taxes_insurance_monthly", "utilities_monthly",
                    "ask_price", "offer_price",
                }
                _values = {}
                for state_key, csv_col in _loadable.items():
                    if csv_col not in row.index:
                        continue
                    if state_key in _numeric:
                        _values[state_key] = safe_float(row[csv_col], default_values.get(state_key, 0))
                    else:
                        _values[state_key] = safe_text(row[csv_col])
                return _values

            for _card_idx, (_, _row) in enumerate(_cards.iterrows(), 1):
                _address = safe_text(_row.get("property_address"))
                _listing_url = safe_text(_row.get("listing_url"))
                _title = _address or _listing_url or f"Saved deal {_card_idx}"
                _status = normalize_pipeline_status(_row.get("deal_status"))
                _quality = safe_text(_row.get("deal_quality"), "Unknown")
                _confidence = safe_text(_row.get("revenue_confidence"), "Unknown")
                _saved_at = safe_text(_row.get("updated_at")) or safe_text(_row.get("saved_at"), "Unknown")
                _max_offer = safe_float(_row.get("max_offer"), 0)
                _pass_reason = safe_text(_row.get("pass_reason"))

                info_card(_title, f"Last saved / updated: {_saved_at}")
                _b1, _b2, _b3 = st.columns(3)
                with _b1:
                    status_badge(_status, "danger" if _status == "Passed" else "info")
                with _b2:
                    status_badge(_quality, quality_status(_quality))
                with _b3:
                    status_badge(f"Revenue {_confidence}", confidence_status(_confidence))

                _m1, _m2 = st.columns(2)
                _m1.metric("Offer Price", dollars(safe_float(_row.get("offer_price"), 0)))
                _m2.metric("Max Offer", dollars(_max_offer) if _max_offer else "Not saved")
                _m3, _m4 = st.columns(2)
                _m3.metric("Monthly Net", dollars_month(safe_float(_row.get("monthly_net"), 0)))
                _m4.metric("DSCR", f"{safe_float(_row.get('dscr'), 0):.2f}")
                _m5, _ = st.columns(2)
                _core_irr = safe_float(_row.get("core_five_year_irr"), None)
                _m5.metric("Core IRR", pct(_core_irr) if _core_irr is not None else "N/A")

                if _status == "Passed" and _pass_reason:
                    muted_text(f"Why I passed: {_pass_reason}")

                _action1, _action2 = st.columns(2)
                with _action1:
                    if _listing_url:
                        st.link_button("Open Listing", _listing_url, use_container_width=True)
                with _action2:
                    if st.button("Load Deal", key=f"load_saved_card_{_card_idx}", use_container_width=True):
                        st.session_state["pending_load_saved_deal"] = {
                            "values": _pending_values_from_saved_row(_row),
                            "saved_at": safe_text(_row.get("saved_at")),
                        }
                        st.rerun()

                if _card_idx < len(_cards):
                    st.divider()

        with st.expander("Saved Deals Table", expanded=False):
            _display_cols = [
                "saved_at", "updated_at", "deal_status", "deal_quality",
                "revenue_confidence", "pass_reason", "property_address", "listing_url",
                "offer_price", "max_offer", "monthly_net", "dscr",
                "core_five_year_irr", "deal_notes",
            ]
            _visible_cols = [c for c in _display_cols if c in _pipeline_view.columns]
            _table_view = _pipeline_view[_visible_cols].copy()
            _col_config = {}
            if "listing_url" in _table_view.columns:
                _col_config["listing_url"] = st.column_config.LinkColumn(
                    "Listing",
                    display_text="Open Listing",
                )
            st.dataframe(_table_view, use_container_width=True, hide_index=True, column_config=_col_config)

        st.divider()
        muted_text("Legacy saved-deal loader")

        _status_filter_options = ["All"] + PIPELINE_STATUSES
        _status_filter = st.selectbox("Filter by Deal Status", options=_status_filter_options, key="saved_deals_filter")

        _display_cols = [
            "saved_at", "deal_status", "deal_quality", "property_address", "listing_url", "offer_price",
            "verdict", "monthly_net", "dscr", "core_five_year_irr",
            "revenue_gap_dollars", "deal_notes",
        ]
        _visible_cols = [c for c in _display_cols if c in saved.columns]
        _view = saved[_visible_cols].copy()
        if "deal_status" in _view.columns:
            _view["deal_status"] = _view["deal_status"].apply(normalize_pipeline_status)

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
                _full_saved["deal_status"] = _full_saved["deal_status"].apply(normalize_pipeline_status)
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
                        st.session_state["pending_load_saved_deal"] = {
                            "values": _pending_values_from_saved_row(_load_row),
                            "saved_at": safe_text(_load_row.get("saved_at")),
                        }
                        st.rerun()
