# Property Pocket Handoff V2

## 1. Product Positioning

Property Pocket is a calm, premium acquisition confidence tool for lifestyle real estate investors, busy professionals, and husband/wife investor teams.

Core promise: help users quickly decide whether a property is worth pursuing, what offer price is justified, and what assumptions need verification.

The product is moving beyond a basic underwriting calculator toward a lightweight acquisition operating system: focused on deciding, validating, negotiating, and acting with confidence.

## 2. Current Tech Stack

- Streamlit
- Python
- Current main files:
  - `streamlit-app/app.py`
  - `streamlit-app/underwriting.py`
  - `streamlit-app/scenarios.py`
  - `streamlit-app/verdicts.py`

## 3. Key Architecture Rules

Streamlit widget-backed session keys must not be mutated after their widgets render. This is the most important implementation rule in the app.

Use the pending-state rerun pattern whenever a button needs to update form inputs:

1. Button click stores pending values in `st.session_state`.
2. Button calls `st.rerun()`.
3. Near the top of `app.py`, before widgets render, pending values are applied to widget-backed keys.
4. Pending state is cleared.

This pattern is used for:

- Apply Scenario
- Apply Max Offer
- Load Saved Deal
- Start New Deal

Do not directly mutate widget-backed keys such as `offer_price`, `ask_price`, `listing_url`, `prior_year_annual_income`, `hoa_monthly`, or `taxes_insurance_monthly` after those widgets have been instantiated.

## 4. Current Feature Set

- Deal inputs for property details, pricing, revenue, HOA, taxes/insurance, financing, tax strategy, and exit assumptions.
- Deal Snapshot with key outputs: Monthly Net, DSCR, Core 5-Year IRR, Revenue Gap, and Tax-Enhanced IRR.
- Deal quality tiers:
  - STRONG DEAL
  - CLOSE / FIXABLE
  - UNREALISTIC
- Risk flag engine for cash flow, DSCR, core IRR, revenue confidence, overpaying risk, offer cushion, HOA burden, and taxes/insurance burden.
- Before You Offer checklist that translates underwriting risk into practical diligence steps.
- Solver scenarios for lower offer price, increased annual revenue, reduced HOA, and reduced taxes/insurance.
- Max Offer Solver to identify the highest offer that still hits selected investor targets.
- Market Reality Check for manual nearby comp pressure-testing of revenue and offer assumptions.
- Verify Before Offer section with fast county research access links for appraisal district, property search, tax records, and recorded deeds.
- Saved Deal Dashboard V2 / Acquisition Pipeline with card-style saved deals, simple filters, pipeline statuses, revenue confidence, max offer, and load/open actions.
- Why I Passed field for saved deals marked as Passed.
- Metric Explainers V1 for Monthly Net, DSCR, Core 5-Year IRR, and Revenue Gap.
- Brand System V1 with a restrained premium palette, calm surfaces, subtle cards, badges, and readable metric blocks.

## 5. Product Guardrails

Do not turn Property Pocket into:

- A CRM
- A Zillow clone
- A Bloomberg terminal
- An education platform
- A spreadsheet-heavy model
- A scraping-heavy county data product yet

Stay focused on:

- Acquisition confidence
- Investor clarity
- Trust
- Speed
- Partner-friendly explanations

## 6. Known Constraints

- Most product and UI logic currently lives in `streamlit-app/app.py`.
- No scraping is implemented.
- No APIs are used for property or county data.
- No authentication exists.
- No database migration has been done.
- Saved deals remain CSV-based, lightweight, and backward compatible with older rows.

## 7. Suggested Next Features

Future candidates only:

- Metric Explainers V1.1 for Cash-on-Cash and Equity Multiple
- Deal Memo Export
- Offer Justification Narrative
- Manual county link table for key markets
- Saved Deal Compare View
- Replit migration cleanup

## 8. Verification Command

```powershell
py -m py_compile streamlit-app\app.py streamlit-app\underwriting.py streamlit-app\scenarios.py streamlit-app\verdicts.py
git diff --check
```
