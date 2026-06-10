"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client() -> Groq:
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Step 1: Filter by max_price
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # Step 2: Filter by size (case-insensitive substring match)
    if size is not None:
        size_lower = size.lower().strip()
        listings = [
            item for item in listings
            if size_lower in item["size"].lower()
        ]

    # Step 3: Score each listing by keyword overlap with description
    keywords = set(description.lower().split())

    def score_listing(item: dict) -> int:
        score = 0
        # Check title
        title_words = set(item["title"].lower().split())
        score += len(keywords & title_words) * \
            3  # title matches weighted higher

        # Check description
        desc_words = set(item["description"].lower().split())
        score += len(keywords & desc_words)

        # Check style_tags
        tags_text = " ".join(item["style_tags"]).lower()
        tags_words = set(tags_text.split())
        score += len(keywords & tags_words) * 2  # tags weighted medium

        # Check category
        if item["category"].lower() in keywords:
            score += 2

        return score

    scored = [(item, score_listing(item)) for item in listings]

    # Step 4: Drop zero-score listings
    scored = [(item, s) for item, s in scored if s > 0]

    # Step 5: Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions or general styling advice.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Could not connect to LLM: {e}"

    item_summary = (
        f"New item: {new_item.get('title', 'Unknown item')}\n"
        f"Category: {new_item.get('category', 'N/A')}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Condition: {new_item.get('condition', 'N/A')}\n"
        f"Description: {new_item.get('description', '')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    # Step 1: Check if wardrobe is empty
    if not wardrobe_items:
        prompt = (
            f"A user is considering buying this secondhand item:\n\n"
            f"{item_summary}\n\n"
            f"They don't have a wardrobe entered yet. Give them 2 general outfit ideas "
            f"for this piece — describe what kinds of bottoms, shoes, and layers would "
            f"pair well with it, what aesthetic or vibe it suits, and one specific styling "
            f"tip (like tucking, layering, or accessorizing). Keep it conversational and "
            f"specific — not generic fashion advice."
        )
    else:
        # Format wardrobe for the prompt
        wardrobe_lines = []
        for w_item in wardrobe_items:
            tags = ", ".join(w_item.get("style_tags", []))
            colors = ", ".join(w_item.get("colors", []))
            notes = w_item.get("notes") or ""
            line = f"- {w_item['name']} (ID: {w_item['id']}) | colors: {colors} | tags: {tags}"
            if notes:
                line += f" | notes: {notes}"
            wardrobe_lines.append(line)

        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A user is considering buying this secondhand item:\n\n"
            f"{item_summary}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_text}\n\n"
            f"Suggest 1–2 complete outfit combinations using the new item and specific "
            f"pieces from their wardrobe (reference items by name). For each outfit, "
            f"describe the overall vibe, what goes with what, and one specific styling "
            f"tip. Keep it conversational, like a knowledgeable friend giving advice."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.8,
        )
        result = response.choices[0].message.content.strip()
        if not result:
            raise ValueError("Empty LLM response")
        return result
    except Exception:
        return (
            "Couldn't generate outfit suggestions right now — but this piece would "
            "pair well with your basics and a great pair of shoes."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        Returns a descriptive error string if outfit is empty — does NOT raise.
    """
    # Step 1: Guard against empty outfit
    if not outfit or not outfit.strip():
        return (
            "Can't generate a fit card without an outfit suggestion — "
            "run suggest_outfit first."
        )

    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Could not connect to LLM: {e}"

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price", "unknown price")
    platform = new_item.get("platform", "a thrift platform")
    style_tags = ", ".join(new_item.get("style_tags", []))

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok caption for this thrifted outfit.\n\n"
        f"The new thrifted item: {title} — ${price} from {platform}\n"
        f"Style vibe: {style_tags}\n"
        f"Outfit details: {outfit}\n\n"
        f"Rules for the caption:\n"
        f"- Write in casual, first-person voice like a real OOTD post (not a product description)\n"
        f"- Mention the item name, price, and platform naturally — once each\n"
        f"- Capture the specific outfit vibe in a few words\n"
        f"- Can include 1–2 relevant emojis\n"
        f"- Should feel authentic and slightly different each time\n"
        f"- Do NOT use hashtags\n\n"
        f"Write only the caption, nothing else."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=1.2,  # Higher temperature for variety
        )
        result = response.choices[0].message.content.strip()
        if not result:
            raise ValueError("Empty LLM response")
        return result
    except Exception:
        return (
            "Fit card unavailable right now, but trust — this look is giving."
        )
