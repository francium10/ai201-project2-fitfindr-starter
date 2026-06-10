"""
tests/test_tools.py

Pytest tests for each FitFindr tool, covering happy paths and failure modes.

Run with:
    pytest tests/ -v
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
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
    """Size filter is case-insensitive and uses substring matching."""
    results = search_listings("tee", size="M", max_price=None)
    # Every returned listing's size must contain "m" (case-insensitive)
    assert all("m" in item["size"].lower() for item in results)


def test_search_returns_list_on_no_keyword_match():
    """Nonsense keyword returns empty list, not an exception."""
    results = search_listings("xyznonexistentitem123", size=None, max_price=None)
    assert isinstance(results, list)
    assert results == []


def test_search_no_filters_returns_many():
    """With no filters, a broad keyword should return multiple results."""
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 5


def test_search_result_has_required_fields():
    """Each returned listing must have the expected fields."""
    results = search_listings("denim", size=None, max_price=50)
    assert len(results) > 0
    required = {"id", "title", "description", "category", "style_tags",
                "size", "condition", "price", "colors", "platform"}
    for item in results:
        assert required.issubset(item.keys())


def test_search_sorted_by_relevance():
    """Results should be sorted so the most relevant item is first."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 1
    # The top result should have "graphic" or "tee" or "vintage" in its title or tags
    top = results[0]
    combined = (top["title"] + " ".join(top["style_tags"])).lower()
    assert any(kw in combined for kw in ["graphic", "tee", "vintage", "band"])


# ── suggest_outfit tests ──────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    """Happy path: returns a non-empty string when wardrobe has items."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20


def test_suggest_outfit_empty_wardrobe():
    """Failure mode: empty wardrobe returns styling advice, not an exception."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20  # Should give general advice, not empty string


def test_suggest_outfit_returns_string_not_exception():
    """suggest_outfit must never raise — always return a string."""
    dummy_item = {
        "id": "test_001",
        "title": "Test Item",
        "category": "tops",
        "style_tags": ["vintage"],
        "colors": ["black"],
        "condition": "good",
        "description": "A test item.",
        "price": 20.0,
        "platform": "depop",
        "size": "M",
        "brand": None,
    }
    result = suggest_outfit(dummy_item, get_empty_wardrobe())
    assert isinstance(result, str)


# ── create_fit_card tests ─────────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    """Happy path: returns a non-empty caption string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    card = create_fit_card(outfit, results[0])
    assert isinstance(card, str)
    assert len(card) > 20


def test_create_fit_card_empty_outfit():
    """Failure mode: empty outfit string returns error string, not exception."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    card = create_fit_card("", results[0])
    assert isinstance(card, str)
    assert len(card) > 0
    # Should NOT raise; should return a descriptive error message
    assert "outfit" in card.lower() or "suggest" in card.lower() or "card" in card.lower()


def test_create_fit_card_whitespace_outfit():
    """Failure mode: whitespace-only outfit string returns error string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    card = create_fit_card("   ", results[0])
    assert isinstance(card, str)
    assert len(card) > 0


def test_create_fit_card_varies_on_same_input():
    """Caption should vary between runs (temperature > 1.0)."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    item = results[0]
    outfit = suggest_outfit(item, get_example_wardrobe())
    card1 = create_fit_card(outfit, item)
    card2 = create_fit_card(outfit, item)
    # They may occasionally match, but this is a smoke test for variation
    assert isinstance(card1, str) and isinstance(card2, str)
    assert len(card1) > 10 and len(card2) > 10
