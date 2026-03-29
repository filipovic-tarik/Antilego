# LOGOS V1 — Build Plan & AI-Assisted Development Guide

## How to Read This Document

This document is the **project blueprint** for building LOGOS V1. It answers three questions:

1. **What do humans need to do?** (math, curation, decisions)
2. **What can AI code for us?** (and how do we prompt it)
3. **What order do we build things in?**

Everything is organized into phases. Each phase has a clear deliverable, a list of human tasks, and a list of AI-promptable tasks with example prompts you can adapt.

---

## The Big Picture: What You're Actually Building

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌────────────┐    ┌──────────┐
│  Polymarket  │───▶│  Snapshot    │───▶│  Family       │───▶│  Optimize  │───▶│  Metrics │
│  Live Data   │    │  Collector   │    │  Builder +    │    │  (cvxpy)   │    │  + Plots │
│  (live.py)   │    │  (JSON/CSV)  │    │  Constraints  │    │            │    │          │
└─────────────┘    └──────────────┘    └───────────────┘    └────────────┘    └──────────┘
     YOU HAVE            PHASE 2             PHASE 3            PHASE 4          PHASE 5
      THIS                                                                    
```

You already have the leftmost piece (live.py + orderbook.py). The rest gets built left-to-right.

---

## Phase 0: Human-Only Work (No Coding)

**Time: Days 1–3 | Who: Both of you**

This is the most important phase. AI cannot do this for you — it requires judgment, math understanding, and manual research on Polymarket.

### Task 0A: Go to Polymarket and Find Real Market Families

Open [polymarket.com](https://polymarket.com) and manually find groups of related markets. You need at least **2–3 families** to start. Here's what to look for:

**Threshold Chains (easiest to find):**
Browse crypto or price markets. Look for groups like:
- "Will BTC be above $X by [date]?" at multiple thresholds

Write down each market's:
- Full title
- Current price (= implied probability)
- **Asset ID** (this is in the URL or API — you'll need this for live.py)

**Mutually Exclusive Sets (also common):**
Look for election or competition markets:
- "Who will win [election]?" → Candidate A, B, C, etc.
- These should sum to ~1.0

**Deadline Nesting (if you can find them):**
Same event at different dates:
- "Will X happen by March?" / "...by June?" / "...by December?"

**Deliverable:** A spreadsheet or notes doc with:

| Family Name | Family Type | Market Title | Asset ID | Current Price |
|---|---|---|---|---|
| BTC Thresholds June | threshold_chain | BTC > 95k by June | abc123... | 0.48 |
| BTC Thresholds June | threshold_chain | BTC > 100k by June | def456... | 0.35 |
| BTC Thresholds June | threshold_chain | BTC > 105k by June | ghi789... | 0.22 |
| Election 2026 | mutually_exclusive | Candidate A wins | jkl012... | 0.45 |
| Election 2026 | mutually_exclusive | Candidate B wins | mno345... | 0.38 |
| Election 2026 | mutually_exclusive | Candidate C wins | pqr678... | 0.15 |

> **This is the single most important human task.** If the families are wrong or poorly chosen, the whole project breaks. Spend real time here.

### Task 0B: Write Out the Math by Hand

Before any code, write the math on paper (or LaTeX). Your partner (the optimization person) should lead this, but both of you should understand it.

**For each family type, write:**

1. **The variable vector:** p = [p₁, p₂, ..., pₙ]
2. **The constraints:**
   - Threshold chain: p₁ ≥ p₂ ≥ ... ≥ pₙ , and 0 ≤ pᵢ ≤ 1
   - Deadline nesting: p₁ ≤ p₂ ≤ ... ≤ pₙ , and 0 ≤ pᵢ ≤ 1
   - Mutually exclusive (exhaustive): Σpᵢ = 1, and 0 ≤ pᵢ ≤ 1
   - Mutually exclusive (non-exhaustive): Σpᵢ ≤ 1, and 0 ≤ pᵢ ≤ 1
3. **The objective:** minimize Σ wᵢ(pᵢ - pᵢᵐᵃʳᵏᵉᵗ)² (start with wᵢ = 1)
4. **Work through one example by hand.** Take three fake prices like [0.48, 0.52, 0.22] for a threshold chain. The violation is that 0.52 > 0.48 for the harder threshold. What should the projected values be? Solve it on paper or with a calculator.

**Why this matters:** When you hand the optimization to AI, you need to be able to verify the output. If you haven't done it by hand once, you won't catch bugs.

**Deliverable:** A page of handwritten or typed math showing the formulation + one worked example per family type.

### Task 0C: Decide on Your Data Strategy

You have two options and should pick one:

| | Option A: Snapshots | Option B: Live Stream |
|---|---|---|
| **How** | Poll the REST API every N minutes, save to JSON | Use live.py websocket, log orderbook state |
| **Pros** | Simpler, easier to debug, works in Jupyter | Real-time, already have code for it |
| **Cons** | Misses fast changes | Harder to use in Jupyter, more complex |
| **Recommendation** | **Start here for V1** | Add later if time allows |

**Our recommendation: Option A for the Jupyter notebook.** Use the Polymarket REST API (CLOB client) to fetch prices at intervals and save snapshots. The websocket code (live.py) is great for a live demo but harder to integrate into a notebook-based research workflow.

---

## Phase 1: Environment Setup

**Time: Day 3–4 | Who: Either of you**

### What AI Can Do For You

Prompt for your AI coding assistant:

> "I'm building a Python project called LOGOS that analyzes Polymarket prediction markets. Set up a Jupyter notebook with the following imports and verify they work: `py_clob_client`, `cvxpy`, `numpy`, `pandas`, `matplotlib`, `seaborn`, `json`, `datetime`. Also install any missing packages. Show me a requirements.txt."

### What You Need to Do (Human)

- Get your Polymarket API key set up (follow py_clob_client docs)
- Test that your key works by running the connection code from live.py
- Confirm you can fetch data for at least one asset ID

### Deliverable

A notebook cell that runs clean with all imports, and a second cell that successfully connects to Polymarket and prints a price.

---

## Phase 2: Data Collection Pipeline

**Time: Days 4–7 | Who: Caleb (data side)**

### The Goal

Build a system that fetches current prices for your curated market families and saves timestamped snapshots.

### What AI Can Do For You

**Prompt 1 — Schema definition:**

> "Create a Python dataclass or dictionary schema for a 'MarketFamily' with these fields: family_name (str), family_type (one of: threshold_chain, deadline_nesting, nested_achievement, mutually_exclusive), markets (list of dicts with fields: title, asset_id, current_price, timestamp). Include a function to validate that a family has at least 2 markets. Give me example data matching this schema for a BTC threshold chain family."

**Prompt 2 — Snapshot collector:**

> "Using the py_clob_client Python package for Polymarket, write a function called `fetch_family_snapshot(client, family_config)` that takes a ClobClient and a family config dict (containing asset_ids and family metadata) and returns a timestamped snapshot of current prices for all assets in the family. The family config looks like this: [paste your Phase 0 spreadsheet data here]. Save each snapshot as a JSON line in a .jsonl file."

**Prompt 3 — Batch collection loop:**

> "Write a collection loop that runs `fetch_family_snapshot` for all my families every 5 minutes for N iterations, saving results to a JSONL file. Include error handling so one failed API call doesn't crash the whole loop. Print a status update after each round."

### What You Need to Do (Human)

- **Paste your real family data** (from Phase 0) into the AI prompts. The AI doesn't know which markets you picked.
- **Run the collector** for a few hours to get real data. Ideally run it overnight or over a weekend to get meaningful time-series data.
- **Spot-check the data**: open the JSONL file, verify prices look reasonable (between 0 and 1), timestamps are correct, asset IDs match what you expect.

### Deliverable

A JSONL file with 50+ timestamped snapshots of your market families. A notebook section that loads and displays this data in a pandas DataFrame.

---

## Phase 3: Family Builder & Constraint Engine

**Time: Days 7–12 | Who: Both (partner leads math, Caleb leads structure)**

### The Goal

Take raw snapshots and organize them into typed families with the right constraints attached.

### What AI Can Do For You

**Prompt 1 — Family builder class:**

> "Create a Python class called `FamilyBuilder` that takes a list of market family configs (each has a name, type, and list of asset_ids) and a snapshot DataFrame. It should return structured Family objects where each family has: name, type, an ordered list of (market_title, observed_probability) pairs, and a method `get_constraints()` that returns the appropriate constraint description for the family type.
>
> The four family types and their constraints are:
> - threshold_chain: p[0] >= p[1] >= ... >= p[n] (descending, ordered by threshold ascending)
> - deadline_nesting: p[0] <= p[1] <= ... <= p[n] (ascending, ordered by deadline ascending)  
> - nested_achievement: p[0] >= p[1] >= ... >= p[n] (descending, ordered by achievement difficulty)
> - mutually_exclusive: sum(p) == 1 (or sum(p) <= 1 if not exhaustive)"

**Prompt 2 — Violation checker:**

> "Write a function `check_violations(family)` that takes a Family object and returns a dict with: `has_violation` (bool), `violation_details` (list of which specific constraints are broken), and `violation_magnitude` (sum of constraint breaches). For a threshold_chain, a violation means p[i] < p[i+1] for some i. For mutually_exclusive, a violation means sum(p) > 1.001 or sum(p) < 0.999."

### What You (The Human) Need to Do

- **Verify constraint logic**: When AI writes the constraint checker, test it against your hand-worked examples from Phase 0B. If your hand math said [0.48, 0.52, 0.22] is a violation, the code should too.
- **Order the markets correctly within each family.** The AI doesn't know that "$95k threshold" should come before "$100k threshold" — you need to specify the ordering.
- **Decide the tolerance**: Markets won't violate by exactly 0. You need to pick a threshold (e.g., violations only count if the breach exceeds 0.005 or 0.01). This is a judgment call.

### Deliverable

A notebook section that loads snapshot data, builds families, and prints a table showing which families have violations at each timestamp.

---

## Phase 4: Convex Optimization (The Core Math)

**Time: Days 12–18 | Who: Partner leads, Caleb reviews**

### The Goal

For each family snapshot that has a violation, compute the nearest coherent probability vector using cvxpy.

### What AI Can Do For You

**Prompt — The projector (this is the key prompt of the whole project):**

> "Using cvxpy, write a function called `project_to_coherent(observed_probs, family_type, exhaustive=True)` that:
>
> 1. Takes a numpy array of observed market probabilities and a family type string
> 2. Defines a cvxpy variable vector p of the same length
> 3. Sets the objective to minimize: sum of (p[i] - observed[i])^2
> 4. Adds constraints based on family_type:
>    - 'threshold_chain': p[i] >= p[i+1] for all consecutive pairs, plus 0 <= p <= 1
>    - 'deadline_nesting': p[i] <= p[i+1] for all consecutive pairs, plus 0 <= p <= 1
>    - 'nested_achievement': same as threshold_chain
>    - 'mutually_exclusive': sum(p) == 1 if exhaustive, sum(p) <= 1 otherwise, plus 0 <= p <= 1
> 5. Solves the problem and returns: the optimal p* values, the per-market adjustments (p* - observed), and the family inconsistency score (L2 norm of the adjustment vector)
>
> Include error handling for infeasible problems. Test it with this example: observed = [0.48, 0.52, 0.22] for a threshold_chain — the result should have p[0] >= p[1] >= p[2] and be close to [0.50, 0.50, 0.22] (verify this is approximately correct)."

### What You (The Human) Need to Do

- **Verify against your hand calculation.** This is critical. Run the optimizer on your Phase 0B example and check it matches what you computed by hand. If it doesn't match, debug before moving on.
- **Test edge cases**: What happens when there's no violation? (Answer: p* should equal p_observed.) What happens when all probabilities are 0.5 in a mutually exclusive set of 3? (Answer: should project to [0.33, 0.33, 0.33].)
- **Understand the output.** You need to be able to explain in plain English what the optimizer is doing: "It finds the closest set of probabilities that don't violate the logical rules."

### Deliverable

A notebook section that, for each violated family snapshot, shows a clean table:

| Market | Observed | Coherent (p*) | Adjustment |
|---|---|---|---|
| BTC > 95k | 0.48 | 0.50 | +0.02 |
| BTC > 100k | 0.52 | 0.50 | -0.02 |
| BTC > 105k | 0.22 | 0.22 | 0.00 |

**Family Inconsistency Score: 0.028**

---

## Phase 5: Metrics & Empirical Analysis

**Time: Days 18–23 | Who: Both**

### The Goal

Answer the three research questions: How often? How big? How long?

### What AI Can Do For You

**Prompt 1 — Frequency analysis:**

> "Given a pandas DataFrame with columns [timestamp, family_name, family_type, has_violation, inconsistency_score], compute and plot:
> 1. What fraction of snapshots have at least one violation, grouped by family type (bar chart)
> 2. A time series of violation count per snapshot (line chart)
> 3. A summary table of violation frequency per family"

**Prompt 2 — Magnitude analysis:**

> "From the same DataFrame plus per-market adjustment data, compute and plot:
> 1. Distribution of inconsistency scores across all family-snapshots (histogram)
> 2. Average and max per-market adjustment by family type (grouped bar chart)
> 3. Box plot of inconsistency scores by family type"

**Prompt 3 — Persistence analysis:**

> "Compute violation persistence: for each family, identify consecutive runs of snapshots where has_violation is True. Calculate the average and median run length. Plot a histogram of violation durations. If snapshot interval is 5 minutes, convert to real time."

### What You (The Human) Need to Do

- **Interpret the results.** AI can make the charts but can't tell you what they mean for market efficiency. You need to write 2–3 paragraphs explaining: Are violations common or rare? Are they big or small? Do they persist or vanish quickly? What does this say about Polymarket's efficiency?
- **Identify interesting findings.** Maybe one family type is way more inconsistent than others. Maybe violations spike around news events. These observations are what make it research.

### Deliverable

A notebook section with 4–6 clean charts and a written interpretation.

---

## Phase 6: Polish & Presentation

**Time: Days 23–28 | Who: Both**

### The Goal

Make the notebook look like a research deliverable, not a coding scratchpad.

### What AI Can Do For You

> "Take this Jupyter notebook and reorganize it into these sections with markdown headers and explanations between each code cell:
> 1. **Title & Abstract** (2–3 sentence project summary)
> 2. **Motivation** (why prediction market coherence matters)
> 3. **Mathematical Framework** (constraints and optimization formulation in LaTeX)
> 4. **Data** (what markets we tracked, how long, how many snapshots)
> 5. **Results: Violation Detection** (which families violated, examples)
> 6. **Results: Coherent Projection** (before/after tables, adjustment analysis)
> 7. **Results: Empirical Analysis** (frequency, magnitude, persistence)
> 8. **Discussion** (what we found, limitations, future work)
> Add clean markdown explanations between code cells. Use LaTeX for any math."

### What You (The Human) Need to Do

- **Write the narrative** sections (Motivation, Discussion). AI can draft these but you should rewrite them in your voice.
- **Pick the best examples** to showcase. Don't show every family — pick 2–3 that tell the best story.
- **Proofread everything.** Check that numbers in text match numbers in tables/charts.

---

## Summary: Human vs. AI Task Split

| Task | Who Does It | Why It Can't Be Automated |
|---|---|---|
| Find real market families on Polymarket | **Human** | Requires browsing, judgment, domain understanding |
| Write out math formulation by hand | **Human** | Need to understand it to verify code |
| Pick asset IDs and ordering within families | **Human** | Requires understanding what the markets mean |
| Decide violation tolerance threshold | **Human** | Judgment call with no "correct" answer |
| Verify optimizer output against hand calc | **Human** | Trust-but-verify — the whole project depends on this |
| Interpret empirical results | **Human** | What do the numbers *mean*? |
| Write motivation and discussion sections | **Human** | Your voice, your framing |
| All code implementation | **AI-assisted** | Schema, API calls, optimization, plotting |
| Chart formatting and notebook styling | **AI-assisted** | Tedious formatting work |
| LaTeX math rendering in notebook | **AI-assisted** | Syntax is fiddly, AI handles it well |

---

## Tips for Prompting AI Coding Assistants

1. **Always paste your actual data structures.** Don't say "my data" — paste a real example JSON object or DataFrame row. The AI needs to see the shape of your data.

2. **One task per prompt.** Don't ask for the whole pipeline at once. Ask for one function, test it, then move on.

3. **Include test cases.** End every prompt with "Test it with this input: ... The expected output should be approximately: ..."

4. **When something breaks, paste the full error.** Don't paraphrase the error — copy the entire traceback.

5. **Save working code before iterating.** When a cell works, copy it somewhere safe before asking AI to modify it. 

6. **Use Claude's artifact/file features for longer code.** For anything over 20 lines, ask the AI to create a .py file rather than inline code.

---

## Recommended Notebook Cell Structure

```
Cell 1:  [Markdown]  Title, authors, date, abstract
Cell 2:  [Code]      Imports and setup
Cell 3:  [Code]      API connection test
Cell 4:  [Markdown]  Section 1: Motivation (your writing)
Cell 5:  [Markdown]  Section 2: Mathematical Framework (LaTeX)
Cell 6:  [Code]      Family config definitions (your curated families)
Cell 7:  [Code]      Data loading (load your collected snapshots)
Cell 8:  [Code]      Family builder + show raw data tables
Cell 9:  [Markdown]  Section 3: Violation Detection
Cell 10: [Code]      Run violation checker, display results
Cell 11: [Markdown]  Section 4: Coherent Projection
Cell 12: [Code]      Run optimizer, display before/after tables
Cell 13: [Markdown]  Section 5: Empirical Analysis
Cell 14: [Code]      Frequency charts
Cell 15: [Code]      Magnitude charts
Cell 16: [Code]      Persistence charts
Cell 17: [Markdown]  Section 6: Discussion & Conclusion
Cell 18: [Markdown]  References / Appendix
```

---

## Week-by-Week Calendar

| Week | Phase | Key Deliverable |
|---|---|---|
| **Week 1** | Phase 0 + 1 + start of 2 | Families curated, math on paper, environment working, data collection started |
| **Week 2** | Phase 2 + 3 | Snapshot data collected, family builder done, violation checker working |
| **Week 3** | Phase 4 + 5 | Optimizer verified, metrics computed, charts generated |
| **Week 4** | Phase 5 + 6 | Analysis complete, notebook polished, narrative written |

**The number one risk is spending too long on Phase 2 (data plumbing).** Set a hard deadline: if data collection isn't working by end of Week 1, simplify. You can always hardcode a few manual snapshots to keep the rest of the project moving.

---

*This document is your roadmap. Print it, check things off, and refer back to it when you're unsure what to work on next.*
