"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

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
    """
    Initialize and return a fresh session dict for one user interaction.
    """
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Parse the user's natural language query into structured parameters.

    Uses the LLM to extract description, size, and max_price.
    Falls back to regex-based parsing if the LLM call fails.

    Returns:
        dict with keys: description (str), size (str|None), max_price (float|None)
    """
    # --- LLM-based parsing (primary) ---
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
        import json
        text = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()
        parsed = json.loads(text)
        return {
            "description": str(parsed.get("description", query)),
            "size": parsed.get("size") or None,
            "max_price": float(parsed["max_price"]) if parsed.get("max_price") else None,
        }
    except Exception:
        pass

    # --- Regex fallback ---
    description = query

    # Extract size (e.g. "size M", "size XL", "in a S")
    size = None
    size_match = re.search(
        r"\b(?:size\s+)?([XSML]{1,3}|XS|SM|ML|XL|XXL|XXXL|\d+)\b",
        query,
        re.IGNORECASE,
    )
    if size_match:
        size = size_match.group(1).upper()

    # Extract max price (e.g. "under $30", "less than $50", "max $40", "$25 max")
    max_price = None
    price_match = re.search(
        r"(?:under|less than|max|below|up to)\s*\$?\s*(\d+(?:\.\d+)?)"
        r"|\$\s*(\d+(?:\.\d+)?)\s*(?:max|or less)",
        query,
        re.IGNORECASE,
    )
    if price_match:
        raw = price_match.group(1) or price_match.group(2)
        max_price = float(raw)

    # Clean up description: remove price and size phrases
    description = re.sub(
        r"(?:under|less than|max|below|up to)\s*\$?\s*\d+(?:\.\d+)?", "", description
    )
    description = re.sub(
        r"\$\s*\d+(?:\.\d+)?\s*(?:max|or less)?", "", description)
    description = re.sub(
        r"\bsize\s+[XSML]{1,3}\b", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\s{2,}", " ", description).strip(" ,.")

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        The session dict. Check session["error"] first — if not None,
        the interaction ended early and outfit_suggestion/fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse query into structured parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    # Step 3a: Early exit if no results
    if not results:
        size_hint = f" size {size}" if size else ""
        price_hint = f" under ${max_price:.0f}" if max_price else ""
        session["error"] = (
            f"No listings found for \"{description}\"{size_hint}{price_hint}. "
            f"Try broadening your search — remove the size filter, raise your price "
            f"ceiling, or use different keywords (e.g. 'band tee' instead of 'graphic shirt')."
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
        print(f"Found:    {session['selected_item']['title']}")
        print(f"Parsed:   {session['parsed']}")
        print(f"\nOutfit:\n{session['outfit_suggestion']}")
        print(f"\nFit card:\n{session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

    print("\n\n=== Empty wardrobe path ===\n")
    session3 = run_agent(
        query="vintage cardigan under $40",
        wardrobe=get_empty_wardrobe(),
    )
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"Found:    {session3['selected_item']['title']}")
        print(f"\nOutfit:\n{session3['outfit_suggestion']}")
        print(f"\nFit card:\n{session3['fit_card']}")
