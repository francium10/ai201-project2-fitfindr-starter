"""
app.py

Gradio interface for FitFindr. Calls run_agent() and maps session results
to three output panels.

Run with:
    python app.py

Then open the URL shown in your terminal (usually http://localhost:7860).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:      The text the user typed into the search box.
        wardrobe_choice: "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        (listing_text, outfit_suggestion, fit_card) — one string per output panel.
    """
    # Step 1: Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query to get started.", "", ""

    # Step 2: Select wardrobe
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # Step 3: Run the agent
    session = run_agent(user_query.strip(), wardrobe)

    # Step 4: Handle early-exit error
    if session["error"]:
        return session["error"], "", ""

    # Step 5: Format the selected listing into a readable string
    item = session["selected_item"]
    brand = item.get("brand") or "Unknown brand"
    colors = ", ".join(item.get("colors", []))
    style_tags = ", ".join(item.get("style_tags", []))
    all_results = session.get("search_results", [])
    result_count = len(all_results)

    listing_text = (
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

    return listing_text, session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
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
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
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

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
