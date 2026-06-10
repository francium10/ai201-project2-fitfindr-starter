# FitFindr 🛍️

A multi-tool AI agent that helps users find secondhand clothing pieces and figure out how to wear them. FitFindr searches mock thrift listings, suggests outfit combinations based on your existing wardrobe, and generates a shareable fit card caption — all from a single natural language query.

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

---

## Tool Inventory

### Tool 1: `search_listings`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `description` (str), `size` (str \| None), `max_price` (float \| None) |
| **Output** | `list[dict]` — matching listing dicts sorted by relevance score |
| **Purpose** | Searches the 40-item mock listings dataset by keyword overlap across title, description, and style_tags. Filters by price ceiling and size before scoring. |

Each listing dict returned contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str|None), `platform` (str).

### Tool 2: `suggest_outfit`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `new_item` (dict), `wardrobe` (dict with `items` key) |
| **Output** | `str` — 1–2 outfit suggestions referencing specific wardrobe pieces |
| **Purpose** | Calls Groq LLM (llama-3.3-70b-versatile) to generate outfit combinations using the thrifted item and the user's existing wardrobe. Falls back to general styling advice if wardrobe is empty. |

### Tool 3: `create_fit_card`

| | |
|---|---|
| **File** | `tools.py` |
| **Inputs** | `outfit` (str), `new_item` (dict) |
| **Output** | `str` — a 2–4 sentence Instagram/TikTok caption |
| **Purpose** | Calls Groq LLM at temperature=1.2 to generate a casual, authentic OOTD caption. Mentions item name, price, and platform naturally. Produces different output each run. |

---

## How the Planning Loop Works

The planning loop in `run_agent()` (`agent.py`) follows conditional logic — it does not call all tools unconditionally:

```
1. Parse query → extract description, size, max_price (via LLM with regex fallback)
2. Call search_listings(description, size, max_price)
   → If results is EMPTY: set session["error"] and RETURN EARLY
     (suggest_outfit and create_fit_card are NOT called)
   → If results has items: set selected_item = results[0], continue
3. Call suggest_outfit(selected_item, wardrobe)
   → If outfit is empty: set session["error"] and RETURN EARLY
   → Otherwise: store in session["outfit_suggestion"], continue
4. Call create_fit_card(outfit_suggestion, selected_item)
   → Store in session["fit_card"]
5. Return completed session
```

The key behavioral difference: if `search_listings` returns nothing, the agent stops immediately with an actionable error message and never attempts to suggest an outfit with empty input.

---

## State Management

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. No state persists between sessions.

| Key | Set when | Used by |
|-----|----------|---------|
| `query` | initialization | query parser |
| `parsed` | after query parsing | search_listings call |
| `search_results` | after search_listings | selected_item assignment |
| `selected_item` | after non-empty results | suggest_outfit, create_fit_card |
| `wardrobe` | initialization | suggest_outfit |
| `outfit_suggestion` | after suggest_outfit | create_fit_card |
| `fit_card` | after create_fit_card | app.py Panel 3 |
| `error` | any failure | app.py Panel 1 (error display) |

`app.py`'s `handle_query()` receives the completed session and maps keys directly to the three Gradio output panels.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match query | Sets `session["error"]`: "No listings found for '[description]'. Try broadening your search — remove the size filter, raise your price ceiling, or use different keywords." Returns session early — suggest_outfit is never called. |
| `suggest_outfit` | Wardrobe is empty | Calls LLM with a general styling prompt instead of wardrobe-specific outfit combos. Returns advice like what bottoms, shoes, and layers pair well with the item. Never raises or returns empty string. |
| `create_fit_card` | `outfit` param is empty or whitespace | Returns error string: "Can't generate a fit card without an outfit suggestion — run suggest_outfit first." Does not raise an exception. |

**Concrete example from testing:**

Query: `"designer ballgown size XXS under $5"`

```
search_listings("designer ballgown", size="XXS", max_price=5.0)
→ returns []
→ session["error"] = "No listings found for 'designer ballgown' size XXS under $5.
   Try broadening your search..."
→ suggest_outfit: NOT called
→ create_fit_card: NOT called
→ app.py displays error in Panel 1, Panels 2 and 3 are empty
```

---

## Spec Reflection

**One way the spec helped:** Filling out the planning loop section of `planning.md` with explicit conditional branches before writing code made it immediately clear that `run_agent()` needed two early-return points, not one. Without the spec, it would have been easy to accidentally call `suggest_outfit` with `None` as the item.

**One way implementation diverged from spec:** The query parser was originally planned as pure regex. During implementation, an LLM-based parser was added as the primary method (with regex as fallback) because natural language queries like "I mostly wear baggy jeans and chunky sneakers, looking for a vintage tee" don't parse well with simple patterns. The fallback still exists for cases where the LLM call fails.

---

## AI Usage

**Instance 1 — search_listings implementation:**
Input to Claude: the Tool 1 spec block from `planning.md` (inputs, return value, failure mode) and the listings.json field list. Asked it to implement using `load_listings()` and score by keyword overlap across title, description, and style_tags with weighted scoring (title 3x, tags 2x, description 1x). Reviewed the generated code and adjusted the size matching from exact match to case-insensitive substring match (so "M" matches "S/M") after noticing the listings use composite sizes.

**Instance 2 — planning loop implementation:**
Input to Claude: the full Architecture ASCII diagram and the Planning Loop + State Management table from `planning.md`. Asked it to implement `run_agent()` following the exact conditional branches described. Reviewed the output and added an additional guard for empty `outfit_suggestion` (Step 5a) which the generated code omitted — the spec described it but the generated implementation skipped it.

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover happy paths and all three failure modes:
- `search_listings` with matching query, no-match query, price filter, size filter
- `suggest_outfit` with populated wardrobe and empty wardrobe
- `create_fit_card` with valid outfit, empty outfit string, whitespace-only outfit

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
│   └── test_tools.py          # pytest tests for all tools and failure modes
├── planning.md                # Agent spec — filled out before implementation
├── tools.py                   # search_listings, suggest_outfit, create_fit_card
├── agent.py                   # run_agent() planning loop
├── app.py                     # Gradio interface
├── requirements.txt
└── .env                       # GROQ_API_KEY (not committed)
```