"""
app.py

Gradio interface for FitFindr. Calls run_agent() and maps session results
to three output panels. Includes style profile memory (stretch feature).

Run with:
    python app.py
"""

import gradio as gr

from agent import run_agent
from tools import compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from style_memory import load_profile, save_profile, update_profile_from_session, get_profile_summary


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(
    user_query: str,
    wardrobe_choice: str,
    use_memory: bool,
) -> tuple[str, str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns:
        (listing_text, outfit_suggestion, fit_card, price_comparison, profile_display)
    """
    # Step 1: Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query to get started.", "", "", "", ""

    # Step 2: Load style profile if memory is enabled
    profile = load_profile() if use_memory else None

    # Step 3: Select wardrobe — prefer memory choice if available
    if use_memory and profile and profile.get("wardrobe_choice"):
        wardrobe_choice = profile["wardrobe_choice"]

    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # Step 4: Augment query with profile preferences if memory enabled
    query = user_query.strip()
    if use_memory and profile and profile.get("size") and "size" not in query.lower():
        query += f" size {profile['size']}"

    # Step 5: Run the agent
    session = run_agent(query, wardrobe)

    # Step 6: Handle early-exit error
    if session["error"]:
        error_msg = session["error"]
        if session.get("retry_note"):
            error_msg = f"ℹ️ {session['retry_note']}\n\n{error_msg}"
        return error_msg, "", "", "", get_profile_summary(profile) if profile else ""

    # Step 7: Update and save style memory
    if use_memory and profile is not None:
        profile["wardrobe_choice"] = wardrobe_choice
        profile = update_profile_from_session(profile, session)
        save_profile(profile)

    # Step 8: Format listing output
    item = session["selected_item"]
    brand = item.get("brand") or "Unknown brand"
    colors = ", ".join(item.get("colors", []))
    style_tags = ", ".join(item.get("style_tags", []))
    result_count = len(session.get("search_results", []))

    retry_banner = ""
    if session.get("retry_note"):
        retry_banner = f"ℹ️  {session['retry_note']}\n\n"

    listing_text = (
        f"{retry_banner}"
        f"🛍️  {item['title']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰  Price:      ${item['price']:.2f}\n"
        f"📦  Platform:   {item['platform'].capitalize()}\n"
        f"📏  Size:       {item['size']}\n"
        f"✅  Condition:  {item['condition'].capitalize()}\n"
        f"🎨  Colors:     {colors}\n"
        f"🏷️  Brand:      {brand}\n"
        f"🔖  Style:      {style_tags}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝  {item['description']}\n\n"
        f"({result_count} listing{'s' if result_count != 1 else ''} found — showing top match)"
    )

    # Step 9: Price comparison (stretch feature)
    price_assessment = compare_price(item)

    # Step 10: Profile display
    profile_display = get_profile_summary(profile) if (use_memory and profile) else ""

    return (
        listing_text,
        session["outfit_suggestion"],
        session["fit_card"],
        price_assessment,
        profile_display,
    )


def clear_profile() -> str:
    """Clear the saved style profile."""
    import os
    from style_memory import MEMORY_FILE
    if os.path.exists(MEMORY_FILE):
        os.remove(MEMORY_FILE)
        return "Style profile cleared."
    return "No profile to clear."


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
    "vintage tee size XS under $10",         # retry logic demo
]


def build_interface():
    with gr.Blocks(title="FitFindr", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
# FitFindr 🛍️
**Find secondhand pieces and get outfit ideas based on your wardrobe.**
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            with gr.Column(scale=1):
                wardrobe_choice = gr.Radio(
                    choices=["Example wardrobe", "Empty wardrobe (new user)"],
                    value="Example wardrobe",
                    label="Wardrobe",
                )
                use_memory = gr.Checkbox(
                    label="💾 Remember my style preferences",
                    value=False,
                )

        submit_btn = gr.Button("Find it 🔍", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=12,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=12,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=12,
                interactive=False,
            )

        with gr.Row():
            price_output = gr.Textbox(
                label="💰 Price assessment",
                lines=5,
                interactive=False,
            )
            profile_output = gr.Textbox(
                label="📋 Your style profile (memory)",
                lines=8,
                interactive=False,
            )

        with gr.Row():
            clear_btn = gr.Button("🗑️ Clear style profile", variant="secondary")

        gr.Examples(
            examples=[[q, "Example wardrobe", False] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice, use_memory],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, use_memory],
            outputs=[listing_output, outfit_output, fitcard_output, price_output, profile_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, use_memory],
            outputs=[listing_output, outfit_output, fitcard_output, price_output, profile_output],
        )
        clear_btn.click(
            fn=clear_profile,
            inputs=[],
            outputs=[profile_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
