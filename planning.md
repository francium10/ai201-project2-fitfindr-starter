# FitFindr — planning.md

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items that match the user's description, optional size, and optional price ceiling. Returns a ranked list of matching listings sorted by keyword relevance.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for (e.g., "vintage graphic tee"). Used for keyword scoring against title, description, and style_tags.
- `size` (str | None): Size string to filter by (e.g., "M", "S/M"). Case-insensitive. Pass None to skip size filtering.
- `max_price` (float | None): Maximum price (inclusive). Pass None to skip price filtering.

**What it returns:**
A list of matching listing dicts, sorted by relevance score (highest first). Each dict contains:
`id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]),
`size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str|None), `platform` (str).
Returns an empty list `[]` if no listings match — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to: *"No listings found for '[query]'. Try broadening your search — remove the size filter, raise your price ceiling, or use different keywords."* It returns the session immediately and does NOT call suggest_outfit or create_fit_card.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item the user is considering and their existing wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations using the new piece and named items from the wardrobe.

**Input parameters:**
- `new_item` (dict): A listing dict from search_listings — the item the user is considering buying.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. May be empty.

**What it returns:**
A non-empty string with 1–2 outfit suggestions. Each suggestion names specific wardrobe pieces and describes the overall vibe. If the wardrobe is empty, returns general styling advice for the item instead.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the LLM is prompted for general styling advice (what kinds of pieces pair well, what aesthetic it suits). If the LLM call fails, returns a fallback string: *"Couldn't generate outfit suggestions right now — but this piece would pair well with your basics and a great pair of shoes."*

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual, shareable outfit caption — the kind of thing you'd post on Instagram or TikTok with your OOTD. Calls the LLM with higher temperature to ensure variety across runs.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by suggest_outfit.
- `new_item` (dict): The listing dict for the thrifted item (provides title, price, platform).

**What it returns:**
A 2–4 sentence string written in casual, first-person social media voice. Naturally mentions the item name, price, and platform once each. Captures the specific outfit vibe. Returns a descriptive error string if `outfit` is empty — never raises an exception.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, returns: *"Can't generate a fit card without an outfit suggestion — run suggest_outfit first."* If the LLM call fails, returns: *"Fit card unavailable right now, but trust — this look is giving."*

---

### Additional Tool: compare_price (Stretch)

**What it does:**
Given a listing, compares its price to similar listings in the dataset and tells the user whether it's a good deal, average, or overpriced.

**Input parameters:**
- `item` (dict): A listing dict to evaluate.

**What it returns:**
A string summarizing the price comparison (e.g., "This is priced below average for vintage tops in this condition — solid deal.").

**What happens if it fails or returns nothing:**
Returns: *"Not enough comparable listings to assess price for this item."*

---

## Planning Loop

After initializing the session, the agent parses the user's query using the LLM to extract `description`, `size`, and `max_price`. It then follows this conditional logic:

1. Call `search_listings(description, size, max_price)` → store in `session["search_results"]`
2. **If `search_results` is empty:** set `session["error"]` with a specific, actionable message and **return early** — do not proceed to steps 3–6.
3. **If `search_results` is not empty:** set `session["selected_item"] = search_results[0]` (top result)
4. Call `suggest_outfit(selected_item, wardrobe)` → store in `session["outfit_suggestion"]`
5. **If `outfit_suggestion` is empty or an error string:** set `session["error"]` and return early.
6. Call `create_fit_card(outfit_suggestion, selected_item)` → store in `session["fit_card"]`
7. Return the completed session.

The loop only proceeds to the next step if the previous step succeeded. It never calls `suggest_outfit` with an empty item, and never calls `create_fit_card` with an empty outfit.

---

## State Management

All state is stored in a single `session` dict initialized by `_new_session()` at the start of each interaction. The session is passed through each step and returned at the end.

| Key | Set in | Used by |
|-----|--------|---------|
| `query` | initialization | query parsing step |
| `parsed` | query parsing | search_listings call |
| `search_results` | after search_listings | selected_item assignment |
| `selected_item` | after search_results check | suggest_outfit, create_fit_card |
| `wardrobe` | initialization | suggest_outfit |
| `outfit_suggestion` | after suggest_outfit | create_fit_card |
| `fit_card` | after create_fit_card | app.py output panel |
| `error` | any failure point | app.py error display |

No state is stored between sessions (each run_agent() call starts fresh).

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]`: "No listings found for '[description]'. Try removing the size filter, raising your price ceiling, or using different keywords like 'band tee' instead of 'graphic shirt'." Returns session early. |
| suggest_outfit | Wardrobe is empty | Calls LLM with general styling prompt instead: "Your wardrobe is empty, so here are some general styling ideas for this piece: [LLM response]" |
| create_fit_card | Outfit input is empty or whitespace | Returns error string: "Can't generate a fit card without an outfit suggestion — run suggest_outfit first." Does not raise exception. |

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────┐
│              Planning Loop                  │
│  run_agent(query, wardrobe)                 │
│                                             │
│  Step 1: _new_session()                     │
│  Step 2: LLM query parsing                  │
│     → session["parsed"] =                  │
│       {description, size, max_price}        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
      search_listings(description, size, max_price)
                   │
          ┌────────┴────────┐
          │                 │
     results=[]        results=[item,...]
          │                 │
          ▼                 ▼
   session["error"]   session["search_results"]
   "No listings..."   session["selected_item"] = results[0]
   return session ◄        │
   (early exit)            ▼
                  suggest_outfit(selected_item, wardrobe)
                           │
                  ┌────────┴────────┐
                  │                 │
            wardrobe empty     wardrobe has items
                  │                 │
                  ▼                 ▼
          general styling   specific outfit combos
                  └────────┬────────┘
                           │
                  session["outfit_suggestion"]
                           │
                           ▼
              create_fit_card(outfit_suggestion, selected_item)
                           │
                  session["fit_card"]
                           │
                           ▼
                    return session
                           │
                           ▼
                  app.py → 3 output panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings:** Give Claude the Tool 1 spec block (inputs, return value, failure mode) and the listings.json field list. Ask it to implement using `load_listings()` from `utils/data_loader.py`, filtering by price and size, then scoring by keyword overlap with title + description + style_tags. Verify: does it filter all three parameters? Does it return `[]` on no match without raising? Test with 3 queries (graphic tee, impossible query, no-size query).

- **suggest_outfit:** Give Claude the Tool 2 spec, the wardrobe_schema.json structure, and a sample listing dict. Ask it to implement using Groq `llama-3.3-70b-versatile`. Verify: does it handle empty wardrobe? Does it name specific wardrobe items in the output? Test with example wardrobe and empty wardrobe.

- **create_fit_card:** Give Claude the Tool 3 spec and the caption style guidelines. Ask it to set temperature=1.2. Verify: does it return an error string (not exception) on empty outfit? Run it 3 times on the same input and confirm outputs differ. Confirm it mentions price and platform naturally.

**Milestone 4 — Planning loop and state management:**

Give Claude the full Architecture diagram and the Planning Loop + State Management tables from this file. Ask it to implement `run_agent()` in agent.py using the exact conditional logic described. Verify before running: does it branch on empty search_results? Does it store values in the correct session keys? Does it NOT call suggest_outfit when search is empty? Test both happy path and no-results path.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Query Parsing:**
The agent calls the LLM to extract structured parameters from the query:
- `description` = "vintage graphic tee"
- `size` = None (not specified)
- `max_price` = 30.0

**Step 2 — search_listings("vintage graphic tee", size=None, max_price=30.0):**
Loads all 40 listings. Filters to items under $30. Scores remaining items by keyword overlap with "vintage graphic tee" against each listing's title, description, and style_tags. Returns ranked results. Top match: `lst_006` — "Graphic Tee — 2003 Tour Bootleg Style" at $24.00 (depop), style_tags: ["graphic tee", "vintage", "grunge", "streetwear", "band tee"]. Also matches: `lst_033` "Vintage Band Tee — Faded Grey" at $19.00.
Session: `selected_item` = lst_006 dict.

**Step 3 — suggest_outfit(lst_006, example_wardrobe):**
The LLM receives the item details and the user's 10-item wardrobe. It suggests: "Pair this boxy bootleg tee with your baggy straight-leg jeans (w_001) and chunky white sneakers (w_007) for a classic 90s streetwear look. Tuck the front corner slightly for shape. Add the black crossbody bag (w_010) to keep it clean. For a grungier take, swap the sneakers for your black combat boots (w_008) and layer the vintage black denim jacket (w_006) over the top."
Session: `outfit_suggestion` = above string.

**Step 4 — create_fit_card(outfit_suggestion, lst_006):**
The LLM generates: "thrifted this 2003 bootleg tee off depop for $24 and i genuinely cannot stop wearing it 🖤 styled it with my baggy jeans and chunky sneakers for that effortless 90s thing — full look in my stories"
Session: `fit_card` = above string.

**Final output to user:**
- Panel 1 (listing): "Graphic Tee — 2003 Tour Bootleg Style | $24.00 | depop | Size: L | Condition: good | Style: graphic tee, vintage, grunge, streetwear"
- Panel 2 (outfit): The suggest_outfit string above
- Panel 3 (fit card): The create_fit_card caption above