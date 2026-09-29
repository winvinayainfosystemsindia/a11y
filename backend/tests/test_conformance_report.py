"""Unit tests for app.utils.conformance_report - the IAAP Accessibility
Conformance Certificate builder that fills the firm's own .docx template
with a real audit run's results."""
import io

import docx
import pytest

from app.utils.conformance_report import _remarks_for_criterion, _rollup_conformance, build_conformance_certificate
from app.utils.wcag_criteria import WCAG_LEVEL_A, WCAG_LEVEL_AA_ADDITIONAL


def _row(status, tc_name="TC", **kw):
    d = {"status": status, "tc_name": tc_name, "actual_result": "", "remediation": ""}
    d.update(kw)
    return d


# ---- _rollup_conformance ----------------------------------------------------

def test_rollup_all_pass_supports():
    assert _rollup_conformance([_row("pass"), _row("pass")]) == "Supports"


def test_rollup_all_fail_does_not_support():
    assert _rollup_conformance([_row("fail"), _row("fail")]) == "Does Not Support"


def test_rollup_mixed_pass_and_fail_partially_supports():
    assert _rollup_conformance([_row("pass"), _row("fail")]) == "Partially Supports"


def test_rollup_needs_review_only_not_evaluated():
    assert _rollup_conformance([_row("needs_review")]) == "Not Evaluated"


def test_rollup_fail_beats_needs_review():
    """A confirmed failure must never be masked by an ambiguous review row."""
    assert _rollup_conformance([_row("fail"), _row("needs_review")]) == "Does Not Support"


def test_rollup_empty_not_evaluated():
    assert _rollup_conformance([]) == "Not Evaluated"


# ---- _remarks_for_criterion --------------------------------------------------

def test_remarks_supports_mentions_count():
    remarks = _remarks_for_criterion("Non-text Content", [_row("pass"), _row("pass")], "Supports", in_scope=True)
    assert "2" in remarks
    assert "met the requirement" in remarks


def test_remarks_does_not_support_names_failing_instance():
    rows = [_row("fail", tc_name="Search button name check", remediation="Add aria-label.")]
    remarks = _remarks_for_criterion("Name, Role, Value", rows, "Does Not Support", in_scope=True)
    assert "Search button name check" in remarks
    assert "Add aria-label" in remarks


def test_remarks_out_of_scope_explains_why():
    remarks = _remarks_for_criterion("Captions (Live)", [], "Not Evaluated", in_scope=False)
    assert "outside the conformance level" in remarks


def test_remarks_no_rows_in_scope_says_not_covered():
    remarks = _remarks_for_criterion("Some Criterion", [], "Not Evaluated", in_scope=True)
    assert "not covered" in remarks


# ---- build_conformance_certificate (end-to-end) -----------------------------

@pytest.fixture()
def sample_results():
    return {
        "project_name": "Acme Corp Homepage",
        "page_title": "Acme Corp - Home",
        "page_url": "https://acme.example.com/",
        "conformance_level": "AA",
        "test_cases": [
            _row("pass", tc_name="Logo alt text check", criteria="1.1.1 Non-text Content"),
            _row("fail", tc_name="Body text contrast check", criteria="1.4.3 Contrast (Minimum)",
                 remediation="Increase contrast. Measured 2.1:1, needs 4.5:1."),
            _row("needs_review", tc_name="Error message text check", criteria="3.3.1 Error Identification",
                 description="AI could not determine if the message is understandable."),
        ],
        "defects": [],
        "report": {},
    }


@pytest.fixture()
def generated_doc(sample_results):
    docx_bytes = build_conformance_certificate(sample_results)
    return docx.Document(io.BytesIO(docx_bytes))


def test_produces_exactly_three_tables(generated_doc):
    """Standards table + Level A + Level AA - the template's original 14
    sample per-page table chunks must be fully removed, not left alongside."""
    assert len(generated_doc.tables) == 3


def test_level_a_table_has_all_32_criteria(generated_doc):
    table = generated_doc.tables[1]
    assert len(table.rows) - 1 == len(WCAG_LEVEL_A) == 32


def test_level_aa_table_has_all_24_criteria(generated_doc):
    table = generated_doc.tables[2]
    assert len(table.rows) - 1 == len(WCAG_LEVEL_AA_ADDITIONAL) == 24


def test_standards_table_does_not_falsely_claim_untested_standards(generated_doc):
    """This platform evaluates WCAG 2.0/2.1/2.2 A+AA - it must never claim
    India-specific BIS/GIGWA standards were checked."""
    table = generated_doc.tables[0]
    by_label = {row.cells[0].text.strip(): row.cells[1].text.strip() for row in table.rows[1:]}
    assert "Yes" in by_label["Web Content Accessibility Guidelines 2.0"] or "Level A" in by_label[
        "Web Content Accessibility Guidelines 2.0"]
    assert by_label["BIS IS17802"] == "Not Evaluated"
    assert by_label["GIGWA 3.0"] == "Not Evaluated"


def test_criteria_rows_reflect_actual_run_results(generated_doc):
    by_sc = {}
    for table in (generated_doc.tables[1], generated_doc.tables[2]):
        by_sc.update({row.cells[0].text.split(" ", 1)[0]: row for row in table.rows[1:]})
    assert by_sc["1.1.1"].cells[1].text == "Supports"  # Level A
    assert by_sc["1.4.3"].cells[1].text == "Does Not Support"  # Level AA
    assert "2.1:1" in by_sc["1.4.3"].cells[2].text
    assert by_sc["3.3.1"].cells[1].text == "Not Evaluated"  # Level A


def test_untested_criteria_still_get_a_row(generated_doc):
    """Every one of the 50 criteria must appear even if this run's page had
    no test case for it - never silently drop a row from the certificate."""
    table = generated_doc.tables[1]
    sc_ids = {row.cells[0].text.split(" ", 1)[0] for row in table.rows[1:]}
    assert "2.4.1" in sc_ids  # Bypass Blocks - not in sample_results at all


def test_cover_page_uses_real_run_data(generated_doc):
    texts = [p.text for p in generated_doc.paragraphs[:10]]
    joined = "\n".join(texts)
    assert "Acme Corp Homepage" in joined
    assert "Acme Corp - Home" in joined


def test_stale_page_count_line_removed(generated_doc):
    """The template's static 'Page 1 of 18' is only correct for the
    original example - must not be printed in a generated certificate."""
    for p in generated_doc.paragraphs:
        assert not p.text.strip().startswith("Page 1 of 18")


def test_level_a_conformance_level_marks_level_aa_out_of_scope():
    results = {
        "project_name": "Test", "page_title": "Home", "page_url": "https://x.com/",
        "conformance_level": "A",
        "test_cases": [_row("pass", tc_name="Alt text check", criteria="1.1.1 Non-text Content")],
        "defects": [], "report": {},
    }
    doc = docx.Document(io.BytesIO(build_conformance_certificate(results)))
    level_aa_table = doc.tables[2]
    for row in level_aa_table.rows[1:]:
        assert row.cells[1].text == "Not Evaluated"
        assert "outside the conformance level" in row.cells[2].text
