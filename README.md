# FitFindr 🛍️

A multi-tool AI agent that helps users find secondhand clothing pieces and figure out how to wear them. FitFindr searches mock thrift listings, suggests outfit combinations based on your existing wardrobe, generates a shareable fit card caption, compares item prices to comparable listings, and remembers your style preferences across sessions — all from a single natural language query.

Built for CodePath AI201, Project 2.

---

## Setup

```bash
# 1. Clone your fork
git clone https://github.com/YOUR_USERNAME/ai201-project2-fitfindr-starter.git
cd ai201-project2-fitfindr-starter

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
source .venv/Scripts/activate      # Windows (Git Bash)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file with your Groq API key
echo "GROQ_API_KEY=your_key_here" > .env
```

Get a free Groq API key at [console.groq.com](https://console.groq.com) — no credit card required.

---

## Running the App

```bash
python app.py
```

Open [http://localhost:7860](http://localhost:7860) in your browser.

To run the CLI test (all 3 paths):
```bash
python agent.py
```

To run all tests:
```bash
pytest tests/ -v
```

---

## Tool Inventory

### Tool 1: `search_listings`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `description` (str), `size` (str \| None), `max_price` (float \| None) |
| **Output** | `list[dict]` — matching listing dicts sorted by relevance score, highest first |
| **Purpose** | Searches 40 mock secondhand listings by keyword overlap across title, description, and style_tags. Filters by price ceiling (inclusive) and size (case-insensitive substring match) before scoring. Title matches weighted 3×, style_tag matches 2×, description matches 1×. |

Each dict in the returned list contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str|None), `platform` (str).

### Tool 2: `suggest_outfit`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `new_item` (dict), `wardrobe` (dict with `items` key containing list of wardrobe item dicts) |
| **Output** | `str` — 1–2 outfit suggestions referencing specific wardrobe pieces by name, or general styling advice if wardrobe is empty |
| **Purpose** | Calls Groq LLM (llama-3.3-70b-versatile, temperature=0.8) with the item details and wardrobe contents to generate contextual outfit combinations. Falls back to general styling advice when wardrobe has no items. Never raises an exception. |

### Tool 3: `create_fit_card`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `outfit` (str), `new_item` (dict) |
| **Output** | `str` — a 2–4 sentence Instagram/TikTok caption, or a descriptive error string if outfit is empty |
| **Purpose** | Calls Groq LLM at temperature=1.2 to generate a casual, authentic OOTD caption. Naturally mentions item name, price, and platform once each. Higher temperature ensures different output each run. Returns a specific error string (not exception) if `outfit` is empty or whitespace-only. |

### Stretch Tool: `compare_price`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `item` (dict) — a listing dict with at least `price` (float) and `category` (str) |
| **Output** | `str` — price verdict (🟢/🟡/🟠/🔴) with reasoning, category average, price range, and condition note |
| **Purpose** | Compares the item's price against all other listings in the same category. Calculates mean, median, min, and max prices. Also compares against same-condition listings when 2+ exist. Returns a fallback string if fewer than 3 comparables exist. |

---

## How the Planning Loop Works

The planning loop in `run_agent()` (`agent.py`) uses explicit conditional branching — it does not call all tools in a fixed sequence:

```
Step 1: Initialize session dict (_new_session)
Step 2: Parse query → LLM extracts description, size, max_price
        (regex fallback if LLM call fails)
Step 3: Call _search_with_retry(description, size, max_price)
        → Attempt 1: full constraints (description + size + max_price)
        → If empty + size was set → Attempt 2: drop size filter, keep price
        → If still empty + price was set → Attempt 3: drop both filters
        → If still empty after all retries:
              set session["error"] with actionable message
              RETURN EARLY — suggest_outfit is NOT called
        → If results found:
              set session["selected_item"] = results[0]
              set session["retry_note"] if constraints were loosened
Step 4: Call suggest_outfit(selected_item, wardrobe)
        → If empty response: set session["error"], RETURN EARLY
        → Otherwise: store in session["outfit_suggestion"], continue
Step 5: Call create_fit_card(outfit_suggestion, selected_item)
        → Store in session["fit_card"]
Step 6: Return completed session
```

**Key behavioral difference:** For a no-results query (e.g., "designer ballgown size XXS under $5"), the agent retries with loosened constraints, informs the user of what was adjusted, and if still nothing is found, returns early with a specific error. `suggest_outfit` is never called with a `None` item.

**For a retry-triggered query** (e.g., "vintage tee size XS under $10"): the agent finds no results for size XS under $10, drops the size filter, finds results, and informs the user: *"No exact matches for size 'XS' — showing results for all sizes instead."* It then continues through suggest_outfit and create_fit_card normally.

---

## State Management

All state is stored in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. No state persists between sessions in the core agent (style memory is handled separately by `style_memory.py`).

| Key | Set when | Passed to |
|-----|----------|-----------|
| `query` | initialization | query parser |
| `parsed` | after LLM/regex query parsing | search_listings args |
| `search_results` | after _search_with_retry | selected_item assignment |
| `selected_item` | after non-empty search_results | suggest_outfit, create_fit_card |
| `wardrobe` | initialization | suggest_outfit |
| `outfit_suggestion` | after suggest_outfit | create_fit_card |
| `fit_card` | after create_fit_card | app.py Panel 3 |
| `error` | any failure or early exit | app.py Panel 1 |
| `retry_note` | when constraints were loosened | app.py banner in Panel 1 |

`app.py`'s `handle_query()` reads the completed session and maps keys directly to Gradio output panels — no re-entry by the user at any step.

**State passing verified:** `session["selected_item"]` (set by search step) is passed directly into `suggest_outfit()`. `session["outfit_suggestion"]` (set by suggest step) is passed directly into `create_fit_card()`. Neither requires user re-entry.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match query, even after retry | Sets `session["error"]`: "No listings found for '[description]' even after loosening filters. Try different keywords or remove size/price limits." Returns session early — suggest_outfit and create_fit_card are never called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"] == []`) | Calls LLM with a general styling prompt instead of wardrobe-specific combos. Returns advice like "pair with wide-leg jeans and chunky sneakers for a 90s vibe." Never raises or returns empty string. |
| `create_fit_card` | `outfit` param is empty or whitespace-only | Returns specific error string: "Can't generate a fit card without an outfit suggestion — run suggest_outfit first." Does not raise an exception. |

**Concrete example from testing — no-results path:**

```bash
python -c "
from tools import search_listings
print(search_listings('designer ballgown', size='XXS', max_price=5))
"
# Output: []   ← empty list, no exception raised

# Full agent with same query:
python agent.py
# Error: No listings found for "designer ballgown" size XXS under $5,
#        even after loosening filters. Try different keywords...
```

**Concrete example — empty outfit string:**

```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Output: "Can't generate a fit card without an outfit suggestion —
#          run suggest_outfit first."
```

**Concrete example — retry logic triggered:**

```bash
python -c "
from agent import _search_with_retry
results, note = _search_with_retry('vintage tee', size='XS', max_price=10)
print('Note:', note)
print('Results:', len(results))
"
# Note: No exact matches for size 'XS' — showing results for all sizes instead.
# Results: 3
```

---

## Stretch Features

### Price Comparison Tool (+2pts)

`compare_price(item)` in `tools.py` takes a listing dict and compares its price against all other listings in the same category. It calculates mean, median, min, and max prices and returns a verdict:

- 🟢 Great deal — priced 25%+ below category average
- 🟡 Below average / Fair price — within ±10% of average  
- 🟠 Slightly above average — 10–30% above average
- 🔴 Pricey — 30%+ above average

It also computes a same-condition average when 2+ comparables exist. Shown in the "💰 Price assessment" panel in the Gradio UI.

### Style Profile Memory (+2pts)

`style_memory.py` persists style preferences to `style_profile.json` between sessions. When "Remember my style preferences" is checked in the UI:

- After each successful search, the agent extracts style tags, colors, size, and price from the selected item and saves them to the profile.
- On the next session, if no size is mentioned in the query, the agent automatically appends the remembered size preference.
- The "📋 Your style profile" panel displays current preferences including preferred styles, colors, size, and recent searches.
- Profile can be cleared with the "🗑️ Clear style profile" button.

**Two-session demo:** Search "vintage graphic tee" in session 1 with size M → profile saves size M and vintage/streetwear tags. In session 2, search "cardigan" without mentioning size → agent automatically appends "size M" to the query.

### Retry Logic with Fallback (+1pt)

`_search_with_retry()` in `agent.py` automatically loosens constraints when search returns empty:

1. Try: description + size + max_price (original)
2. If empty + size set → Try: description + max_price only (drop size)
3. If still empty + price set → Try: description only (drop both)

The user is informed of exactly what was adjusted via `session["retry_note"]`, displayed as a banner in the listing panel.

---

## Spec Reflection

**One way the spec helped:** The planning.md Architecture diagram made it immediately clear that `run_agent()` needed two distinct early-return points — one after search, one after suggest_outfit — rather than a single catch-all at the end. Without drawing the flow first, it would have been easy to call `suggest_outfit(None, wardrobe)` and get a hard crash.

**One way implementation diverged from spec:** The query parser was originally planned as pure regex. During implementation, an LLM-based parser was added as the primary method (with regex fallback) because natural language queries like "I mostly wear baggy jeans — looking for a vintage tee" don't parse reliably with patterns. The fallback still exists if the Groq call fails or returns malformed JSON.

---

## AI Usage

**Instance 1 — search_listings implementation:**
Gave Claude the Tool 1 spec block from `planning.md` (inputs, return value, failure mode) and the listings.json field list. Asked it to implement using `load_listings()` with keyword scoring across title, description, and style_tags. Reviewed the generated code and changed size matching from exact string equality to case-insensitive substring matching after noticing that listings use composite sizes like "S/M" and "XL (oversized)". Also added per-field scoring weights (3×/2×/1×) which the generated version treated equally.

**Instance 2 — planning loop and retry logic:**
Gave Claude the full Architecture ASCII diagram and the Planning Loop + State Management table from `planning.md`. Asked it to implement `run_agent()` with the exact conditional branches described. Reviewed the output and added `_search_with_retry()` as a separate function (the generated code inlined the retry which made it harder to test directly). Also added `session["retry_note"]` as a dedicated key — the generated version only communicated retry status through the error field.

---

## Project Structure

```
fitfindr/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe schema + example + empty template
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tests/
│   └── test_tools.py          # pytest tests — all tools + failure modes + retry
├── planning.md                # Agent spec — filled before implementation
├── tools.py                   # search_listings, suggest_outfit, create_fit_card, compare_price
├── agent.py                   # run_agent() planning loop with retry logic
├── app.py                     # Gradio interface — 5 output panels
├── style_memory.py            # Style profile persistence (stretch)
├── style_profile.json         # Auto-created when memory is enabled (gitignored)
├── requirements.txt
└── .env                       # GROQ_API_KEY (not committed)
```
