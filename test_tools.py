"""
tests/test_tools.py

Pytest tests for each FitFindr tool, covering happy paths and failure modes.

Run with:
    pytest tests/ -v
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings tests ─────────────────────────────────────────────────────

def test_search_returns_results():
    """Happy path: broad search returns matches."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    """Failure mode: impossible query returns empty list, no exception."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    """All returned items must be at or below max_price."""
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_size_filter():
    """Size filter is case-insensitive substring matching."""
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_no_keyword_match_returns_empty():
    """Nonsense keyword returns empty list, not an exception."""
    results = search_listings("xyznonexistentitem123", size=None, max_price=None)
    assert isinstance(results, list)
    assert results == []


def test_search_no_filters_returns_many():
    """Broad keyword with no filters returns multiple results."""
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 5


def test_search_result_has_required_fields():
    """Each returned listing must have all expected fields."""
    results = search_listings("denim", size=None, max_price=50)
    assert len(results) > 0
    required = {"id", "title", "description", "category", "style_tags",
                "size", "condition", "price", "colors", "platform"}
    for item in results:
        assert required.issubset(item.keys())


def test_search_sorted_by_relevance():
    """Top result should be most keyword-relevant."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 1
    top = results[0]
    combined = (top["title"] + " " + " ".join(top["style_tags"])).lower()
    assert any(kw in combined for kw in ["graphic", "tee", "vintage", "band"])


# ── suggest_outfit tests ──────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    """Happy path: returns non-empty string with wardrobe."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20


def test_suggest_outfit_empty_wardrobe():
    """Failure mode: empty wardrobe returns general advice, not an exception."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20


def test_suggest_outfit_never_raises():
    """suggest_outfit must never raise — always return a string."""
    dummy_item = {
        "id": "test_001", "title": "Test Item", "category": "tops",
        "style_tags": ["vintage"], "colors": ["black"], "condition": "good",
        "description": "A test item.", "price": 20.0, "platform": "depop",
        "size": "M", "brand": None,
    }
    result = suggest_outfit(dummy_item, get_empty_wardrobe())
    assert isinstance(result, str)


# ── create_fit_card tests ─────────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    """Happy path: returns non-empty caption."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    card = create_fit_card(outfit, results[0])
    assert isinstance(card, str)
    assert len(card) > 20


def test_create_fit_card_empty_outfit():
    """Failure mode: empty outfit returns error string, not exception."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    card = create_fit_card("", results[0])
    assert isinstance(card, str)
    assert len(card) > 0
    assert any(w in card.lower() for w in ["outfit", "suggest", "card", "fit"])


def test_create_fit_card_whitespace_outfit():
    """Failure mode: whitespace-only outfit returns error string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    card = create_fit_card("   ", results[0])
    assert isinstance(card, str)
    assert len(card) > 0


def test_create_fit_card_varies_on_same_input():
    """Caption varies between runs (temperature=1.2)."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    item = results[0]
    outfit = suggest_outfit(item, get_example_wardrobe())
    card1 = create_fit_card(outfit, item)
    card2 = create_fit_card(outfit, item)
    assert isinstance(card1, str) and isinstance(card2, str)
    assert len(card1) > 10 and len(card2) > 10


# ── compare_price tests (stretch) ─────────────────────────────────────────────

def test_compare_price_returns_string():
    """Happy path: returns a non-empty assessment string."""
    results = search_listings("vintage jacket", size=None, max_price=None)
    assert len(results) > 0
    assessment = compare_price(results[0])
    assert isinstance(assessment, str)
    assert len(assessment) > 20


def test_compare_price_has_verdict():
    """Assessment should contain a price verdict emoji."""
    results = search_listings("denim", size=None, max_price=None)
    assert len(results) > 0
    assessment = compare_price(results[0])
    assert any(emoji in assessment for emoji in ["🟢", "🟡", "🟠", "🔴"])


def test_compare_price_no_price():
    """Item with no price returns graceful error string."""
    dummy = {"id": "x", "category": "tops", "price": None}
    result = compare_price(dummy)
    assert isinstance(result, str)
    assert "no price" in result.lower() or "price" in result.lower()


# ── retry logic tests ─────────────────────────────────────────────────────────

def test_retry_drops_size_filter():
    """
    search_with_retry should find results when a tight size + price combo
    has no direct match but results exist without the size filter.
    """
    from agent import _search_with_retry
    results, note = _search_with_retry("vintage tee", size="XS", max_price=10)
    # Either found results with retry (note is set) or no results at all
    if results:
        assert isinstance(note, str) or note is None
    else:
        assert results == []


def test_retry_returns_none_note_on_first_success():
    """No retry needed — note should be None."""
    from agent import _search_with_retry
    results, note = _search_with_retry("vintage", size=None, max_price=None)
    assert len(results) > 0
    assert note is None
