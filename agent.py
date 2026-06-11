"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Includes retry logic with fallback: if search_listings returns no results,
the agent automatically retries with loosened constraints (removes size filter,
then raises price ceiling) before giving up.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set.")
    return Groq(api_key=api_key)


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "retry_note": None,     # set if retry logic was triggered
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Parse the user's natural language query into structured parameters.

    Primary: LLM-based extraction (Groq).
    Fallback: regex-based parsing if LLM call fails.

    Returns:
        dict with keys: description (str), size (str|None), max_price (float|None)
    """
    # LLM-based parsing (primary)
    try:
        client = _get_groq_client()
        prompt = (
            f"Extract search parameters from this clothing query. "
            f"Return ONLY a JSON object with these keys:\n"
            f"- description: the item being searched for (str)\n"
            f"- size: clothing size if mentioned, else null (str or null)\n"
            f"- max_price: maximum price as a number if mentioned, else null (number or null)\n\n"
            f"Query: \"{query}\"\n\n"
            f"Return only valid JSON, no explanation. Example:\n"
            f'{{ "description": "vintage graphic tee", "size": "M", "max_price": 30.0 }}'
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.0,
        )
        text = response.choices[0].message.content.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        parsed = json.loads(text)
        return {
            "description": str(parsed.get("description", query)),
            "size": parsed.get("size") or None,
            "max_price": float(parsed["max_price"]) if parsed.get("max_price") else None,
        }
    except Exception:
        pass

    # Regex fallback
    description = query
    size = None
    size_match = re.search(
        r"\b(?:size\s+)?([XSML]{1,3}|XS|SM|ML|XL|XXL|\d+)\b",
        query, re.IGNORECASE,
    )
    if size_match:
        size = size_match.group(1).upper()

    max_price = None
    price_match = re.search(
        r"(?:under|less than|max|below|up to)\s*\$?\s*(\d+(?:\.\d+)?)"
        r"|\$\s*(\d+(?:\.\d+)?)\s*(?:max|or less)",
        query, re.IGNORECASE,
    )
    if price_match:
        raw = price_match.group(1) or price_match.group(2)
        max_price = float(raw)

    description = re.sub(
        r"(?:under|less than|max|below|up to)\s*\$?\s*\d+(?:\.\d+)?", "", description
    )
    description = re.sub(r"\$\s*\d+(?:\.\d+)?\s*(?:max|or less)?", "", description)
    description = re.sub(r"\bsize\s+[XSML]{1,3}\b", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\s{2,}", " ", description).strip(" ,.")

    return {"description": description, "size": size, "max_price": max_price}


# ── search with retry/fallback ────────────────────────────────────────────────

def _search_with_retry(
    description: str,
    size: str | None,
    max_price: float | None,
) -> tuple[list[dict], str | None]:
    """
    Call search_listings with automatic retry on empty results.

    Retry strategy (loosens constraints one step at a time):
        Attempt 1: description + size + max_price  (original)
        Attempt 2: description + max_price only    (drop size filter)
        Attempt 3: description only                (drop price filter too)

    Returns:
        (results, retry_note) where retry_note describes what was loosened,
        or None if no retry was needed.
    """
    # Attempt 1: original constraints
    results = search_listings(description, size=size, max_price=max_price)
    if results:
        return results, None

    # Attempt 2: drop size filter (if size was set)
    if size is not None:
        results = search_listings(description, size=None, max_price=max_price)
        if results:
            note = (
                f"No exact matches for size '{size}' — "
                f"showing results for all sizes instead."
            )
            return results, note

    # Attempt 3: drop price filter too (if max_price was set)
    if max_price is not None:
        results = search_listings(description, size=None, max_price=None)
        if results:
            parts = []
            if size is not None:
                parts.append(f"size '{size}'")
            parts.append(f"price under ${max_price:.0f}")
            note = (
                f"No matches with {' and '.join(parts)} — "
                f"showing all matching listings regardless of size or price."
            )
            return results, note

    return [], None


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop conditional logic:
        1. Parse query → extract description, size, max_price
        2. Call search_listings (with retry if empty)
           → If still empty after retry: set error, RETURN EARLY
           → If results found: set selected_item = results[0], continue
        3. Call suggest_outfit(selected_item, wardrobe)
           → If empty response: set error, RETURN EARLY
           → Otherwise: store outfit_suggestion, continue
        4. Call create_fit_card(outfit_suggestion, selected_item)
           → Store fit_card
        5. Return completed session

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Completed session dict. Check session["error"] first.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse query
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search with retry fallback
    results, retry_note = _search_with_retry(description, size, max_price)
    session["search_results"] = results
    session["retry_note"] = retry_note

    # Step 3a: Early exit if no results even after retry
    if not results:
        size_hint = f" size {size}" if size else ""
        price_hint = f" under ${max_price:.0f}" if max_price else ""
        session["error"] = (
            f"No listings found for \"{description}\"{size_hint}{price_hint}, "
            f"even after loosening filters. "
            f"Try different keywords (e.g. 'band tee' instead of 'graphic shirt'), "
            f"or remove size and price limits."
        )
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    # Step 5a: Guard against empty outfit
    if not outfit or not outfit.strip():
        session["error"] = (
            "Outfit suggestion came back empty. "
            "Try again or check that your Groq API key is valid."
        )
        return session

    # Step 6: Create fit card
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found:      {session['selected_item']['title']}")
        print(f"Parsed:     {session['parsed']}")
        if session["retry_note"]:
            print(f"Retry note: {session['retry_note']}")
        print(f"\nOutfit:\n{session['outfit_suggestion']}")
        print(f"\nFit card:\n{session['fit_card']}")

    print("\n\n=== No-results path (impossible query) ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error: {session2['error']}")

    print("\n\n=== Retry path: tight size + price ===\n")
    session3 = run_agent(
        query="vintage tee size XS under $10",
        wardrobe=get_example_wardrobe(),
    )
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"Found:      {session3['selected_item']['title']}")
        if session3["retry_note"]:
            print(f"Retry note: {session3['retry_note']}")

    print("\n\n=== Empty wardrobe path ===\n")
    session4 = run_agent(
        query="vintage cardigan under $40",
        wardrobe=get_empty_wardrobe(),
    )
    if session4["error"]:
        print(f"Error: {session4['error']}")
    else:
        print(f"Found: {session4['selected_item']['title']}")
        print(f"\nOutfit (general advice):\n{session4['outfit_suggestion']}")
