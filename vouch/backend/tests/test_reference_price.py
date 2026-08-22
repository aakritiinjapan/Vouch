"""
check_reference_price: is the site's was-price supported by what we recorded before the sale?

This is the only check that judges the SITE rather than our own extraction, so the tests care about
two things the others do not: that a correct scrape of a dubious page still PASSES (the heal is not
at fault), and that the finding carries the two numbers a human needs without any check vocabulary.
"""

from app.guardian.checks import Severity, check_reference_price, profile_run, run_all_checks
from app.guardian.verdict import decide

# What we confirmed before the sale started.
BEFORE_SALE = {
    "Voltmart RTX 5080 Stormbringer 16GB GDDR7": 1149.99,
    "Voltmart RTX 5070 Pulse 12GB GDDR7": 629.99,
}


def _sale_row(name, price, original):
    return {"name": name, "price": price, "original_price": original,
            "shipping": 14.99, "rating": 4.5, "in_stock": True}


def test_inflated_was_price_is_flagged():
    rows = [_sale_row("Voltmart RTX 5080 Stormbringer 16GB GDDR7", 899.99, 1599.99)]
    results = check_reference_price(rows, BEFORE_SALE)

    assert len(results) == 1
    r = results[0]
    assert r.code == "REFERENCE_PRICE_UNSUPPORTED"
    assert r.evidence["claimed_original"] == 1599.99
    assert r.evidence["confirmed_before_sale"] == 1149.99
    assert r.evidence["overstated_by"] == 450.0
    assert r.evidence["current_price"] == 899.99


def test_honest_sale_is_silent():
    """The was-price matches what we recorded, so there is nothing to report."""
    rows = [_sale_row("Voltmart RTX 5080 Stormbringer 16GB GDDR7", 899.99, 1149.99)]
    assert check_reference_price(rows, BEFORE_SALE) == []


def test_a_claim_below_our_record_is_not_a_finding():
    """Understating your own discount harms nobody - only an inflated claim is evidence."""
    rows = [_sale_row("Voltmart RTX 5070 Pulse 12GB GDDR7", 499.99, 599.99)]
    assert check_reference_price(rows, BEFORE_SALE) == []


def test_small_movement_is_inside_tolerance():
    """1% above our last observation is rounding and drift, not an inflated claim."""
    rows = [_sale_row("Voltmart RTX 5070 Pulse 12GB GDDR7", 549.99, 629.99 * 1.01)]
    assert check_reference_price(rows, BEFORE_SALE) == []


def test_products_we_were_not_watching_are_skipped():
    """No prior observation means no basis for a claim - silence, not a guess."""
    rows = [_sale_row("Voltmart RTX 5090 Founders Edition 32GB GDDR7", 1499.99, 2999.99)]
    assert check_reference_price(rows, BEFORE_SALE) == []


def test_no_reference_prices_stands_the_check_down():
    """An ordinary heal validation has no sale to audit and must not invent one."""
    rows = [_sale_row("Voltmart RTX 5080 Stormbringer 16GB GDDR7", 899.99, 9999.99)]
    assert check_reference_price(rows, {}) == []


def test_names_match_case_and_whitespace_insensitively():
    rows = [_sale_row("  voltmart rtx 5070 PULSE 12gb gddr7  ", 499.99, 899.99)]
    assert len(check_reference_price(rows, BEFORE_SALE)) == 1


def test_missing_or_unparseable_claim_is_skipped():
    for original in (None, "", "call for price"):
        rows = [_sale_row("Voltmart RTX 5070 Pulse 12GB GDDR7", 499.99, original)]
        assert check_reference_price(rows, BEFORE_SALE) == [], original


def test_currency_strings_are_coerced():
    rows = [_sale_row("Voltmart RTX 5070 Pulse 12GB GDDR7", "$499.99", "$1,299.99")]
    results = check_reference_price(rows, BEFORE_SALE)
    assert len(results) == 1
    assert results[0].evidence["claimed_original"] == 1299.99


def test_a_correct_scrape_of_a_dubious_page_still_passes():
    """The load-bearing case.

    The extraction is right - we read the page exactly as it is written. The PAGE is making a claim
    its own history does not support. Rejecting the heal for that would punish a good repair for
    something it did not do, so the verdict must stay PASS while the finding is still reported.
    """
    baseline_rows = [_sale_row(n, p, None) for n, p in BEFORE_SALE.items()]
    baseline = profile_run(baseline_rows)

    sale_rows = [
        _sale_row("Voltmart RTX 5080 Stormbringer 16GB GDDR7", 899.99, 1599.99),
        _sale_row("Voltmart RTX 5070 Pulse 12GB GDDR7", 499.99, 1099.99),
    ]
    results = run_all_checks(baseline, sale_rows, len(baseline_rows),
                             is_sample=True, reference_prices=BEFORE_SALE)
    verdict = decide(results)

    codes = {r.code for r in verdict.failures}
    assert "REFERENCE_PRICE_UNSUPPORTED" in codes
    assert verdict.decision == "pass", "a good heal must not be rejected for the site's own claim"
    assert verdict.confirmed is True
    assert all(r.severity is Severity.LOW for r in verdict.failures
               if r.code == "REFERENCE_PRICE_UNSUPPORTED")


def test_the_message_reads_as_an_outcome_not_as_a_check():
    """The product surface shows what a heal protected, never the criteria it was judged by.

    So the message has to stand on its own in plain English: both numbers, who is affected, and no
    check vocabulary a shopper would have to decode.
    """
    rows = [_sale_row("Voltmart RTX 5080 Stormbringer 16GB GDDR7", 899.99, 1599.99)]
    message = check_reference_price(rows, BEFORE_SALE)[0].message

    assert "$1,599.99" in message and "$1,149.99" in message
    assert "$450.00" in message, "the overstatement is the number that matters"
    assert "shopper" in message
    for jargon in ("REFERENCE_PRICE", "check", "tolerance", "severity", "profile", "baseline"):
        assert jargon.lower() not in message.lower(), f"leaked jargon: {jargon}"


def test_a_whole_catalogue_of_fake_claims_is_one_finding_not_thirty():
    """Regression: the first version emitted one result per row.

    Severity is a fixed cost in verdict._score, so 30 inflated rows charged 30 x LOW = 90 points and
    saturated a PASS into a FAIL 10/100 - rejecting a perfectly good extraction because the site lied
    on many rows rather than one. One sale policy is one finding, however many products it covers.
    """
    prior = {f"Product {i}": 100.0 + i for i in range(30)}
    rows = [_sale_row(name, p * 0.7, p * 1.6) for name, p in prior.items()]

    results = check_reference_price(rows, prior)
    assert len(results) == 1, "one policy, one finding"

    ev = results[0].evidence
    assert ev["products_affected"] == 30
    assert ev["products_checked"] == 30
    assert ev["inflated_rate"] == 1.0
    assert len(ev["examples"]) == 5, "examples are capped so evidence stays readable"

    baseline = profile_run([_sale_row(n, p, None) for n, p in prior.items()])
    verdict = decide(run_all_checks(baseline, rows, len(rows), reference_prices=prior))
    assert verdict.decision == "pass", "a good scrape of a dishonest page must still pass"
    assert verdict.confidence == 97, "one LOW finding costs 3"


def test_partial_inflation_reports_the_ratio():
    """Half the catalogue on a fake discount is a different fact from all of it."""
    prior = {f"Product {i}": 100.0 for i in range(10)}
    rows = [_sale_row(f"Product {i}", 70.0, 160.0 if i < 4 else 100.0) for i in range(10)]

    ev = check_reference_price(rows, prior)[0].evidence
    assert ev["products_affected"] == 4
    assert ev["products_checked"] == 10
    assert ev["inflated_rate"] == 0.4
    assert ev["total_overstated"] == 240.0, "4 products x $60 overstated"


def test_reference_prices_omitted_leaves_every_other_check_untouched():
    """Regression guard: adding this check must not change any existing verdict."""
    baseline_rows = [_sale_row(n, p, p * 1.1) for n, p in BEFORE_SALE.items()]
    baseline = profile_run(baseline_rows)
    clean = [_sale_row(n, p, p * 1.1) for n, p in BEFORE_SALE.items()]

    verdict = decide(run_all_checks(baseline, clean, len(baseline_rows), is_sample=True))
    assert verdict.decision == "pass"
    assert verdict.confidence == 100
