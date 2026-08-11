"""Unit tests for the Success Criteria Library data (app.utils.wcag_criteria)."""
from app.utils.wcag_criteria import (
    ELEMENT_TYPES,
    WCAG_TO_AXE_RULES,
    all_success_criteria,
    axe_rules_for_criterion,
    principle_for_criterion,
    success_criteria_for_level,
)

_EXPECTED_21_CRITERIA = {
    "1.3.4", "1.3.5", "1.4.10", "1.4.11", "1.4.12", "1.4.13",
    "2.1.4", "2.5.1", "2.5.2", "2.5.3", "2.5.4", "4.1.3",
}


def test_all_success_criteria_has_exactly_fifty_rows():
    criteria = all_success_criteria()
    assert len(criteria) == 50


def test_no_duplicate_sc_numbers():
    criteria = all_success_criteria()
    sc_numbers = [c.sc_number for c in criteria]
    assert len(sc_numbers) == len(set(sc_numbers))


def test_sorted_numerically_by_sc_number():
    criteria = all_success_criteria()
    sc_numbers = [c.sc_number for c in criteria]
    assert sc_numbers == sorted(sc_numbers, key=lambda s: tuple(int(p) for p in s.split(".")))


def test_every_row_has_required_fields_populated():
    for criterion in all_success_criteria():
        assert criterion.sc_number
        assert criterion.name
        assert criterion.wcag_version in {"2.0", "2.1"}
        assert criterion.level in {"A", "AA"}
        assert criterion.guideline
        assert criterion.description


def test_wcag_21_criteria_tagged_correctly():
    by_id = {c.sc_number: c for c in all_success_criteria()}
    for sc_id in _EXPECTED_21_CRITERIA:
        assert by_id[sc_id].wcag_version == "2.1", f"{sc_id} should be tagged WCAG 2.1"
    for sc_id, criterion in by_id.items():
        if sc_id not in _EXPECTED_21_CRITERIA:
            assert criterion.wcag_version == "2.0", f"{sc_id} should be tagged WCAG 2.0"


def test_success_criteria_for_level_a_returns_thirty():
    assert len(success_criteria_for_level("A")) == 30
    assert all(c.level == "A" for c in success_criteria_for_level("A"))


def test_success_criteria_for_level_aa_returns_all_fifty():
    assert len(success_criteria_for_level("AA")) == 50


def test_principle_derived_from_leading_digit():
    assert principle_for_criterion("1.1.1") == "Perceivable"
    assert principle_for_criterion("2.4.3") == "Operable"
    assert principle_for_criterion("3.3.1") == "Understandable"
    assert principle_for_criterion("4.1.2") == "Robust"


def test_element_types_is_a_nonempty_closed_list():
    assert len(ELEMENT_TYPES) > 0
    assert "General Page" in ELEMENT_TYPES
    assert len(ELEMENT_TYPES) == len(set(ELEMENT_TYPES))


def test_wcag_to_axe_rules_covers_every_criterion():
    """Every one of the 50 success criteria must have an explicit entry
    (even if it's []) - a missing key would be indistinguishable from "axe
    covers this with zero rules" vs "nobody classified this criterion yet"."""
    all_ids = {c.sc_number for c in all_success_criteria()}
    assert all_ids <= set(WCAG_TO_AXE_RULES.keys())


def test_wcag_to_axe_rules_no_rule_id_shared_across_criteria():
    """Each axe-core rule id must map to exactly one WCAG criterion in the
    table - if the same rule id were listed under two criteria, matching
    would be ambiguous by construction."""
    seen: dict[str, str] = {}
    for sc_id, rule_ids in WCAG_TO_AXE_RULES.items():
        for rule_id in rule_ids:
            assert rule_id not in seen, (
                f"{rule_id!r} listed under both {seen.get(rule_id)!r} and {sc_id!r}"
            )
            seen[rule_id] = sc_id


def test_axe_rules_for_criterion_known_mappings():
    assert axe_rules_for_criterion("1.4.3") == ["color-contrast"]
    assert axe_rules_for_criterion("1.1.1") == ["image-alt", "input-image-alt", "area-alt", "object-alt", "role-img-alt", "svg-img-alt"]
    assert axe_rules_for_criterion("3.1.1") == ["html-has-lang", "html-lang-valid", "html-xml-lang-mismatch"]


def test_axe_rules_for_criterion_empty_for_manual_only_criteria():
    """Criteria axe-core cannot reliably detect must map to [] - callers use
    this to route the step to AI judgment instead of running axe unscoped."""
    for sc_id in ("2.1.4", "1.2.2", "4.1.3", "3.3.1"):
        assert axe_rules_for_criterion(sc_id) == []


def test_axe_rules_for_criterion_unknown_id_returns_empty():
    assert axe_rules_for_criterion("9.9.9") == []
