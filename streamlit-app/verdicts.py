def evaluate(results):
    concerns = []
    strengths = []
    score = 0

    # DSCR
    if results["dscr"] >= 1.25:
        score += 3
        strengths.append(f"Strong DSCR ({results['dscr']:.2f})")
    elif results["dscr"] >= 1.00:
        score += 2
        strengths.append(f"DSCR meets minimum target ({results['dscr']:.2f})")
    else:
        concerns.append(f"DSCR below target ({results['dscr']:.2f})")

    # Monthly cash flow
    if results["monthly_net"] >= 500:
        score += 2
        strengths.append(
            f"Positive monthly net cash flow (${results['monthly_net']:,.0f}/mo)"
        )
    elif results["monthly_net"] >= 0:
        score += 1
        strengths.append("Monthly net cash flow is breakeven or slightly positive")
    else:
        concerns.append(
            f"Negative monthly net cash flow (${results['monthly_net']:,.0f}/mo)"
        )

    # Revenue gap
    if results["revenue_gap_dollars"] <= 0:
        score += 2
        strengths.append("Forecasted revenue clears the DSCR target")
    elif results["revenue_gap_pct"] <= 0.10:
        score += 1
        concerns.append(f"Small revenue gap ({results['revenue_gap_pct']:.1%})")
    else:
        concerns.append(f"Revenue gap is high ({results['revenue_gap_pct']:.1%})")

    # Core IRR before tax strategy
    core_irr = results.get("core_five_year_irr")

    if core_irr is not None and core_irr >= 0.15:
        score += 3
        strengths.append(f"Strong core 5-year IRR ({core_irr:.1%})")
    elif core_irr is not None and core_irr >= 0.08:
        score += 2
        strengths.append(f"Acceptable core 5-year IRR ({core_irr:.1%})")
    elif core_irr is not None and core_irr >= 0.00:
        score += 1
        concerns.append(f"Weak core 5-year IRR ({core_irr:.1%})")
    else:
        concerns.append("Core 5-year IRR is negative or unavailable")

    # Equity multiple
    if results["equity_multiple"] >= 1.75:
        score += 2
        strengths.append(
            f"Strong tax-enhanced equity multiple ({results['equity_multiple']:.2f}x)"
        )
    elif results["equity_multiple"] >= 1.25:
        score += 1
        strengths.append(
            f"Acceptable tax-enhanced equity multiple ({results['equity_multiple']:.2f}x)"
        )
    else:
        concerns.append(f"Equity multiple is low ({results['equity_multiple']:.2f}x)")

    # Tax-enhanced upside, informational only
    tax_irr = results.get("five_year_irr")

    if tax_irr is not None and tax_irr >= 0.25:
        strengths.append(
            f"Large tax-enhanced upside shown by after-tax IRR ({tax_irr:.1%})"
        )

    # Final verdict
    if score >= 9:
        verdict = "BUY"
    elif score >= 5:
        verdict = "REVIEW"
    else:
        verdict = "DO NOT BUY"

    return {
        "verdict": verdict,
        "score": score,
        "reasons": concerns,
        "strengths": strengths,
    }
