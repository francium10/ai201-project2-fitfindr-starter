"""
style_memory.py  [Stretch Feature]

Persists a user's style profile across sessions using a local JSON file.
Stores style preferences extracted from past interactions so the agent
can personalize suggestions without the user re-entering their wardrobe.

Usage:
    from style_memory import load_profile, save_profile, update_profile_from_session
"""

import json
import os
from datetime import datetime

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "style_profile.json")


def load_profile() -> dict:
    """
    Load the user's style profile from disk.

    Returns:
        A profile dict with keys:
            - preferred_styles (list[str]): style tags the user gravitates toward
            - preferred_colors (list[str]): colors that appear frequently
            - size (str | None): most recently used size filter
            - max_price (float | None): most recently used price ceiling
            - past_searches (list[str]): last 10 search descriptions
            - wardrobe_choice (str): "Example wardrobe" or "Empty wardrobe (new user)"
        Returns a fresh empty profile if no file exists.
    """
    if not os.path.exists(MEMORY_FILE):
        return _empty_profile()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_profile()


def save_profile(profile: dict) -> None:
    """
    Save the user's style profile to disk.

    Args:
        profile: The profile dict to persist.
    """
    profile["last_updated"] = datetime.now().isoformat()
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
    except OSError:
        pass  # Fail silently — memory is a nice-to-have, not required


def update_profile_from_session(profile: dict, session: dict) -> dict:
    """
    Update a style profile with information from a completed agent session.

    Extracts style tags, colors, size, and price from the selected item
    and adds them to the running profile. Keeps lists bounded to avoid
    unbounded growth.

    Args:
        profile: Existing profile dict (from load_profile()).
        session: Completed session dict (from run_agent()).

    Returns:
        The updated profile dict (also mutated in place).
    """
    item = session.get("selected_item")
    parsed = session.get("parsed", {})

    if item:
        # Update preferred styles from item's style_tags
        for tag in item.get("style_tags", []):
            if tag not in profile["preferred_styles"]:
                profile["preferred_styles"].append(tag)
        profile["preferred_styles"] = profile["preferred_styles"][-20:]  # keep last 20

        # Update preferred colors
        for color in item.get("colors", []):
            if color not in profile["preferred_colors"]:
                profile["preferred_colors"].append(color)
        profile["preferred_colors"] = profile["preferred_colors"][-15:]

    # Update size and price preferences from parsed query
    if parsed.get("size"):
        profile["size"] = parsed["size"]
    if parsed.get("max_price"):
        profile["max_price"] = parsed["max_price"]

    # Log past searches
    description = parsed.get("description", "")
    if description and description not in profile["past_searches"]:
        profile["past_searches"].append(description)
    profile["past_searches"] = profile["past_searches"][-10:]  # keep last 10

    return profile


def get_profile_summary(profile: dict) -> str:
    """
    Return a human-readable summary of the current style profile.
    Used to display memory state in the Gradio UI.
    """
    if not profile.get("preferred_styles") and not profile.get("past_searches"):
        return "No style profile yet — start searching to build one!"

    styles = ", ".join(profile["preferred_styles"][-5:]) if profile["preferred_styles"] else "none yet"
    colors = ", ".join(profile["preferred_colors"][-5:]) if profile["preferred_colors"] else "none yet"
    size = profile.get("size") or "not specified"
    price = f"${profile['max_price']:.0f}" if profile.get("max_price") else "not specified"
    searches = ", ".join(profile["past_searches"][-3:]) if profile["past_searches"] else "none yet"
    updated = profile.get("last_updated", "never")[:10]

    return (
        f"📋 Your Style Profile (last updated {updated})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 Preferred styles:  {styles}\n"
        f"🎨 Preferred colors:  {colors}\n"
        f"📏 Size preference:   {size}\n"
        f"💰 Price preference:  {price}\n"
        f"🔍 Recent searches:   {searches}"
    )


def _empty_profile() -> dict:
    return {
        "preferred_styles": [],
        "preferred_colors": [],
        "size": None,
        "max_price": None,
        "past_searches": [],
        "wardrobe_choice": "Example wardrobe",
        "last_updated": None,
    }
