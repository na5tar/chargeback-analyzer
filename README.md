# Chargeback Representment Analyzer

**Human-in-the-loop AI-assisted tool** for Checkout.com's Disputes team. The analyst is always the final decision maker — the AI accelerates evidence review and structured assessment, never replaces human judgment.

At scale, this supports **80+ cases per analyst per day** by reducing per-case document review time from ~15 minutes (manual) to ~2 minutes (AI-assisted + analyst verification).

---

## Quick Start

```bash
# 1. Enter directory
cd chargeback-test

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 4. Launch the analyst UI
streamlit run app.py
```

The UI opens at `http://localhost:8501`. Sign in as `analyst_1`, pick a case from the queue, and click **"🔍 Run AI Analysis"**.

---

## Why Kimi (and Why We Pivoted to OpenAI)

**Originally built with Kimi** as default for **5x+ lower cost** (~$0.001–0.003/case vs ~$0.005–0.015/case for OpenAI GPT-4o).

**Pivoted to OpenAI after rigorous latency testing** (5 cases × 2 providers — Kimi and OpenAI):

| Provider | Avg Latency | Tokens/Case | Cost/Case | Verdict |
|----------|-------------|-------------|-----------|---------|
| **Kimi** | 74.3s | ~13,000 | ~$0.002 | 14× slower, 3.6× more tokens |
| **OpenAI GPT-4o** | **5.4s** | ~3,600 | ~$0.010 | **Default** — fastest, most efficient |

**Key finding:** Kimi's lower per-token cost is **offset by verbosity and latency**. At 80 cases/day/analyst, the **~69 seconds saved per case** (74.3s → 5.4s) equals **~92 minutes/day** — nearly **1.5 hours of wait time recovered per analyst**. Kimi remains architecturally supported as a cost-conscious fallback if server performance improves.

**Claude 3.5 Sonnet** is architecturally wired into the multi-provider wrapper (`llm_client.py`) with native Anthropic vision format conversion, but was **not benchmarked** in this exercise. It is reserved for future evaluation on complex reasoning tasks.

---

## Document Ingestion: PDF → LLM Vision

### What We Do
Merchant evidence arrives as PDFs, images, and scans. Instead of extracting text and losing layout, signatures, stamps, and handwritten notes, we:

1. **Convert PDF pages to images** (PNG, 200 DPI) using `pdf2image`
2. **Tier-rank pages** by relevance (case-specific keywords, generic-page penalty)
3. **Send images as base64** to the LLM's vision API alongside structured case metadata

### Why Vision Over Text Extraction

| Approach | Pros | Cons | Why We Rejected It |
|----------|------|------|-------------------|
| **Text extraction** (pdfplumber/OCR) | Fast, cheap, searchable | Loses signatures, stamps, tables, handwriting, layout context | Merchant evidence is often scanned, stamped, or handwritten — text-only misses critical proof |
| **Hybrid** (text + images) | Best of both worlds | Complex pipeline, double token cost | Over-engineered for v1; vision APIs read text natively from images |
| **Vision-only** (our approach) | Preserves all visual context; LLM reads text, signatures, tables natively; single pipeline | Higher token cost per page; slower upload | **Selected** — evidence fidelity is more important than token savings; tiered page selection mitigates cost |

### Why 200 DPI
- **150 DPI**: Blurry text, LLM misreads small print → bad citations
- **200 DPI**: Sweet spot — sharp text, readable signatures, reasonable file size (~200–500 KB/page)
- **300 DPI**: Sharper but 2.25× file size → slower upload, higher token count, marginal accuracy gain

### Interview Prep: Alternatives Considered
- **Native PDF upload** (Claude, some OpenAI models): Not universally supported across all three providers in our wrapper
- **Structured data extraction** (layout-aware parsers like LayoutLM): Requires training data, heavy infra, not multi-provider portable
- **Per-page OCR + text injection**: Tried early; LLM hallucinated on missing signatures and misread table cells

---

## Tiered Page Selection

### The Problem
A typical merchant evidence PDF is 10–50 pages. Sending all pages to the LLM costs:
- **~10,000–50,000 tokens** per case
- **~$0.03–0.15 per case** at OpenAI rates
- **~30–150 seconds** of upload + processing time

Most of those pages are generic: cover sheets, terms of service, blank pages, or unrelated case material. The analyst already knows page 1 is a cover sheet. The AI shouldn't waste tokens on it.

### How It Works

`page_selector.py` scores every page from **0–100** using a weighted keyword search:

```python
def score_page_relevance(page_text, case):
    score = 0

    # HIGH-WEIGHT keywords (case-specific identifiers)
    # +25 points each — these are strong signals the page is about THIS case
    case_id = case['case_id'].lower()          # e.g., "cb-2025-0007"
    txn_id = case['transaction']['transaction_id'].lower()
    merchant_name = case['transaction']['merchant_name'].lower()
    billing_postcode = case['transaction']['billing_address_postcode'].lower()
    shipping_postcode = case['transaction'].get('shipping_address_postcode', '').lower()

    # MEDIUM-WEIGHT keywords (evidence-type indicators)
    # +10 points each — these suggest the page contains evidence
    evidence_keywords = ['delivered', 'tracking', 'signature', 'pod', 
                         'consignment', 'confirmation', 'proof', 'delivery', 
                         'service rendered']

    # GENERIC PAGE PENALTY
    # If the page contains NO case-specific identifiers (case_id or txn_id),
    # the score is capped at 40. This prevents cover sheets, generic terms,
    # and unrelated documents from being auto-sent.
    if case_id not in page_text and txn_id not in page_text:
        score = min(score, 40)

    return min(score, 100)
```

### The Three Tiers

| Tier | Score Threshold | Pages Sent | Action | Rationale |
|------|----------------|------------|--------|-----------|
| **TIER_1** | ≥ 60 | 1–2 pages | Auto-send to LLM | High confidence these pages contain the core evidence. Analyst never sees the rest. |
| **TIER_2** | ≥ 25 | 1–5 pages | Auto-send batch | Moderate confidence. More pages, but still filtered. Analyst can review if needed. |
| **TIER_3** | < 25 | Top 5 pages | Analyst review | Low confidence or no case-specific matches. Analyst manually selects pages. |

### Example

**Case:** CB-2025-0007 (merchant: TechFlow Logistics, reason code: 4855 — Goods Not Received)
**Evidence:** 12-page manifest PDF

| Page | Content | Score | Tier | Sent? |
|------|---------|-------|------|-------|
| 1 | Generic cover sheet | 0 | TIER_3 | No |
| 2 | Terms of service | 5 | TIER_3 | No |
| 3 | **Consignment #TF-2025-4421, collected 22 Apr 2025** | 85 | **TIER_1** | **Yes** |
| 4 | Delivery route map | 35 | TIER_2 | Yes |
| 5 | Driver schedule | 30 | TIER_2 | Yes |
| 6–12 | Blank / generic | 0–10 | TIER_3 | No |

**Result:** 3 of 12 pages sent. **~75% token reduction** for this document.

### OCR Fallback

If `pdfplumber` fails to extract text (scanned PDF, image-based, corrupted), the system falls back to:
1. Convert **all** pages to images via `pdf2image`
2. Send all pages to the LLM with a `tier: OCR_FALLBACK` tag
3. Flag in the analyst UI: *"Document scanned — full vision mode used. Review all pages."*

This is a safety net, not the default. It costs more tokens but preserves evidence fidelity.

### Why This Approach

| Alternative | Why Not Used |
|-------------|-------------|
| **Send full PDF** | 10× token cost, slow, analyst already skips cover sheets manually |
| **Fixed page count** (always send first 3 pages) | Page 3 might be blank; page 7 might have the signature. Keyword scoring is adaptive. |
| **ML page ranker** | Would require training data (analyst page selections). Not viable for 10-case demo. Telemetry captures overrides for future ranker training. |
| **Per-page LLM call** (ask LLM "is this page relevant?") | Double API cost: one call to score, one call to analyze. Heuristic scoring is free. |

### Impact

- **~80–90% token reduction** vs sending full PDFs
- **~$0.02–0.08 saved per case** at OpenAI rates
- **~10–30 seconds saved per case** in upload/processing
- At 80 cases/day: **~$1.60–6.40/day saved per analyst**, **~13–40 minutes/day recovered**

---

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│  cases.json │────▶│  page_selector  │────▶│   analyzer   │
│  (input)    │     │  (tiered docs)  │     │  (LLM layer) │
└─────────────┘     └─────────────────┘     └──────┬───────┘
                                                   │
                            ┌──────────────────────┘
                            ▼
                     ┌─────────────┐
                     │ llm_client  │◀── Multi-provider
                     │  (wrapper)  │    Kimi / OpenAI / Claude
                     └──────┬──────┘
                            │
                     ┌──────┴──────┐
                     │  Provider   │
                     │  Selection  │
                     └─────────────┘
```

### Key Design Decisions

| Decision | Rationale | Impact |
|----------|-----------|--------|
| **Tiered page selection** | Score pages 0-100 with case-specific keywords; generic pages (no case/txn ID) capped at 40 | **~80-90% token reduction** vs sending full PDFs |
| **Deterministic logic engine** | Rules encoded in `reason_code_rules.py` with impossibility detection (AVS/CVV mismatch, no 3DS, new customer) | Prevents LLM hallucination on clear-cut cases; NOT_REPRESENTABLE codes resolved without API call |
| **Systematic evidence flagging** | LLM instructed to flag BURIED_EVIDENCE, CONFIDENT_BUT_IRRELEVANT, CONTRADICTORY | Analysts can verify claims with exact citations |
| **Multi-provider wrapper** | Unified `generate()` interface; metadata routing selects provider by task type | Benchmark against OpenAI; route reasoning tasks to Claude; keep costs low with Kimi |
| **Analyst telemetry loop** | Every override is logged, attributed to reason code, and fed back into prompts | LLM learns from analyst corrections over time |
| **Admin overwrite audit** | `overwrite_decision()` in telemetry.py preserves full history when admins correct resolved cases | Complete audit trail; admin corrections tagged with ADMIN_CORRECTION category |
| **Admin access control** | Password-gated admin mode (dev: `admin123`). Production uses account-bound SSO whitelisting | Prevents unauthorized access to provider override, telemetry reset, and decision overwrite |

---

## Provider Routing

### How It Actually Works (Current Implementation)

**The default is always OpenAI. There is no automatic switching based on case value, volume, or any threshold.**

```python
from llm_client import select_provider

# These are the ONLY ways a provider is selected:

# 1. DEFAULT — always OpenAI, every case, every time
provider = select_provider(task_type="default")        # → "openai"

# 2. BENCHMARK — forces OpenAI for consistency  
provider = select_provider(benchmark=True)              # → "openai"

# 3. COST_SENSITIVE — only triggered programmatically (not in UI/CLI)
provider = select_provider(task_type="cost_sensitive") # → "kimi"

# 4. REASONING — only triggered programmatically (not in UI/CLI)
provider = select_provider(task_type="reasoning")     # → "claude"
```

### In Practice (10-Case Demo)

| How Provider Is Selected | What Happens | Who Can Do It |
|--------------------------|--------------|---------------|
| **Default** (no action) | OpenAI GPT-4o is used | Everyone, every case |
| **Admin override** | Admin clicks "Force Provider" dropdown in admin panel → selects Kimi or Claude | Admin only (⚙️ 3× + `admin123`) |
| **Programmatic** | `task_type="cost_sensitive"` or `task_type="reasoning"` passed in code | Backend only (not exposed in UI/CLI) |

**At 10 cases — or 80 cases — the system never automatically switches providers.** The analyst never sees a provider choice. The admin can force one, but there's no "smart routing" logic yet. That is architecturally supported (the wrapper exists) but not implemented.

### Why Each Provider Exists

| Provider | When You'd Use It | Why | How to Access It |
|----------|-------------------|-----|-----------------|
| **OpenAI GPT-4o** | Every case, by default | Fastest (5.4s), most token-efficient (~3,600 tokens), reliable JSON output. Proven in testing. | Default — no action needed |
| **Kimi** | Cost-sensitive bulk jobs; testing/dev; if OpenAI is down | Lowest cost per token (~$0.002/case). Trade-off: 14× slower, 3.6× more tokens. | Admin force only, or programmatic `task_type="cost_sensitive"` |
| **Claude 3.5 Sonnet** | Complex reasoning tasks; ambiguous evidence; conflicting documents | Stronger long-context reasoning, more nuanced rationale. **Not benchmarked in this exercise.** | Admin force only, or programmatic `task_type="reasoning"` |

### Future: Automatic Routing (Not Implemented)

The architecture supports automatic routing, but it's **not wired up** in the current UI or CLI. A future implementation could:

- Route low-value cases (< $50) to Kimi automatically
- Route cases with confidence 50–80 to Claude for second opinion
- Route NOT_REPRESENTABLE exception checks to Claude for nuanced reasoning

These would require:
1. Case value threshold logic in `select_provider()`
2. Confidence-based routing after initial OpenAI analysis
3. UI/CLI exposure of the `task_type` parameter

**None of this exists today.** The wrapper is ready; the routing logic is not.

---

## Project Structure

```
.
├── analyze_case.py          # CLI entry point
├── analyzer.py              # LLM orchestration + prompt engineering + telemetry hooks
├── llm_client.py            # Multi-provider LLM wrapper
├── telemetry.py             # Analyst override logging, prompt feedback loop, admin overwrite
├── page_selector.py         # Tiered document page selection
├── reason_code_rules.py     # Deterministic logic engine
├── benchmark.py             # Cross-provider benchmarking
├── compare_two_cases.py     # Dev/test script — compare two case analyses side-by-side
├── cases.json               # 10 synthetic chargeback cases
├── documents/               # Merchant evidence PDFs/PNGs
├── telemetry.jsonl          # Append-only override log (auto-created, .gitignore'd)
├── .env.example             # API key template
└── README.md                # This file
```

> **Note:** `compare_two_cases.py` is included for development/testing. It runs two cases through different providers for side-by-side comparison. Not required for production operation.
>
> **Note:** `telemetry.jsonl` is append-only audit data and is `.gitignore`'d. It auto-creates on first decision. Never delete in production without archiving — the audit trail is required for dispute scheme compliance.

---

## Usage

### Single Case Analysis (CLI)

```bash
# Default: auto-selects OpenAI (pivoted from Kimi after latency testing)
python analyze_case.py --case CB-2025-0007

# Explicit provider
python analyze_case.py --case CB-2025-0007 --provider openai

# Benchmark mode (forces OpenAI for consistency)
python analyze_case.py --case CB-2025-0007 --benchmark

# Save output
python analyze_case.py --case CB-2025-0007 --output results/CB-2025-0007.json
```

### Batch Benchmarking

```bash
# Compare Kimi vs OpenAI across all 10 cases
python benchmark.py --providers kimi openai --output benchmark_results.json
```

### Streamlit UI (Analyst-Facing)

```bash
streamlit run app.py
```

The UI includes:
- **User identity** — mock defaults to `analyst_1`. Admin unlock switches identity to `admin`; "🔒 Lock" button reverts to `analyst_1`. All decisions attributed in telemetry.
- **Case queue** with filtering and sorting (by status, scheme, reason code, merchant, value)
- **AI analysis** with evidence assessment and systematic flags
- **Analyst decision** workflow (agree / override with MECE category)
- **Batch processing** for multiple cases
- **Admin mode** — click ⚙️ 3×, enter password (`admin123`), unlock admin controls. "🔒 Lock" button to exit admin mode.
- **Admin overwrite** — admins can correct resolved cases **once**; changes are logged to telemetry with `ADMIN_CORRECTION` category. Further changes require manager escalation.

> **Production note:** The hardcoded password is a development placeholder. In production, admin access is account-bound via SSO whitelisting (e.g., Checkout.com Okta group membership). The password gate in `app.py` is a lightweight stand-in for that authorization layer.

---

## Demo Video Plan

1. **Analyst workflow** — Case 1: Open → Run AI Analysis → Review evidence → Agree with recommendation → Resolved
2. **Admin overwrite** — Case 2: Analyst resolves → Admin unlocks (⚙️ 3× + `admin123`) → Overwrite decision → Logs to telemetry
3. **Telemetry dashboard** — Admin views override rates by provider, reason code breakdown, admin corrections count
4. **Architecture decisions** — Covered in README and interview discussion (not in demo video to keep it under 5 minutes)

---

## Output Format

```json
{
  "case_id": "CB-2025-0007",
  "reason_code": "4855",
  "recommendation": "represent",
  "justification": "All 3 requirements satisfied...",
  "confidence_score": 87,
  "evidence_assessment": [
    {
      "requirement_number": 1,
      "status": "satisfied",
      "document_reference": "manifest.pdf, page 3",
      "citation": "Consignment #TF-2025-4421, collected 22 Apr 2025"
    }
  ],
  "systematic_flags": [
    {
      "flag_type": "BURIED_EVIDENCE",
      "description": "Proof of collection hidden in page 3 of 12-page manifest",
      "location": "manifest.pdf, page 3, line 45"
    }
  ],
  "provider_used": "openai",
  "analysis_mode": "full",
  "llm_tokens_used": 3600
}
```

---

## Safety Limits

| Limit | Value | Location | Rationale |
|-------|-------|----------|-----------|
| Max images per API call | 15 | `analyzer.py` | OpenAI GPT-4o vision API supports up to ~20 images per call in practice, but token count explodes beyond 15. 15 images × ~500 tokens/image = ~7,500 vision tokens, leaving headroom for the text prompt within the 8K response budget. |
| Max images per case | 20 | `analyzer.py` | Merchant evidence rarely exceeds 20 pages for standard disputes. Beyond 20, analyst should manually curate — prevents runaway API costs on edge cases (e.g., merchant dumps 100-page contract). |
| Max tokens per response | 8,000 (full) / 4,000 (minimal) | `analyzer.py` | 8K is GPT-4o's standard output limit. Minimal mode (4K) is a fallback when JSON parsing fails — trades completeness for reliability. Claude supports higher limits but we standardize on the lowest common denominator for portability. |
| Max pages per PDF | 15 | `page_selector.py` | Beyond 15 pages, tiered selection still applies, but we cap to prevent memory issues with `pdf2image` and to signal to the analyst that documents should be split or curated. |
| Max image size | 5 MB | `page_selector.py` | Base64 encoding inflates file size by ~33%. A 5 MB PNG becomes ~6.7 MB in JSON payload. Most API gateways timeout or reject payloads >10 MB. 5 MB keeps us safely under that threshold. |
| Max cases per session | 20 | `analyzer.py` | Streamlit session state is in-memory. 20 cases × ~20 images × ~500 KB = ~200 MB memory footprint. Beyond 20, risk of browser/Streamlit slowdown or crash. Batch processing handles volumes above this. |
| JSON parse retry | Auto-fallback to minimal mode | `analyzer.py` | If the LLM returns malformed JSON (truncated, markdown-wrapped, extra text), retry once with higher tokens. If that fails, strip the prompt to essentials — reduces chance of the LLM getting distracted by verbose instructions. |

---

## Key Features

- **Deterministic short-circuit**: NOT_REPRESENTABLE reason codes (e.g., 10.5, 4870) resolved instantly without LLM call.
- **Requirement applicability filtering**: Requirements tagged with `applies_to` (goods/services/digital) are filtered by case type before being sent to the LLM. Service-only requirements on goods cases are marked `not_applicable` rather than `missing`, preventing false "request more evidence" recommendations. *Note: Code 10.5 includes an explicit conditional — "Recommend accept_liability unless the merchant can prove the transaction was miscoded by the issuer." The deterministic engine flags this as NOT_REPRESENTABLE by default, but the LLM prompt instructs it to check for miscoding evidence if present in merchant documents.*
- **Impossibility detection**: Flags structural gaps (AVS mismatch, no 3DS, new customer) that cannot be fixed with more evidence
- **Tiered page selection**: Only relevant pages sent to LLM; generic cover pages auto-filtered
- **Graceful degradation**: JSON parse failure → retry with higher tokens → fallback to minimal prompt
- **Exact citations**: Every evidence claim includes document name, page number, and line reference
- **Analyst telemetry loop**: Overrides are logged by reason code and classified by discrepancy type (LLM_OVERCONFIDENT, LLM_MISSED_EVIDENCE, etc.). The `telemetry.py` module includes `get_prompt_addendum()` for future feedback loop activation once sufficient data is collected (100+ cases).
- **Admin overwrite audit**: Admins can correct resolved cases via the UI. `overwrite_decision()` in telemetry.py preserves the full decision history and logs the correction with `ADMIN_CORRECTION` category for audit compliance.

---

## Analyst Telemetry & Override Feedback

Every time an analyst overrides the LLM recommendation, the system logs:

| Field | Purpose |
|-------|---------|
| `case_id` | Link back to specific case |
| `reason_code` | Attribute override to scheme rule |
| `llm_recommendation` vs `analyst_override` | What changed |
| `override_reason` | Free-text explanation |
| `discrepancy_type` | Auto-classified (OVERCONFIDENT, MISSED_EVIDENCE, etc.) |
| `confidence_at_override` | LLM confidence when overridden |
| `provider_used` | Which LLM generated the recommendation |
| `analyst_id` | Who made the decision (`analyst_1` or `admin`) |

### Admin Overwrite

When an admin overwrites a resolved case, `telemetry.overwrite_decision()`:
1. Retrieves the case history to preserve the original LLM recommendation
2. Logs a new `ADMIN_CORRECTION` entry with the previous decision context and admin identity
3. Appends to `telemetry.jsonl` (append-only, never mutates history)
4. **One-time only** — subsequent overwrites are blocked with error: *"This case has already been admin-overwritten. Further changes require manager escalation."*

```python
from telemetry import overwrite_decision

# Log an admin correction
overwrite_decision(
    case_id="CB-2025-0007",
    new_choice="represent",
    admin_id="admin_raihan",
    reason="Analyst missed delivery proof on page 3"
)
```

### Feedback Loop (Future Architecture)

The telemetry system is designed to support a future feedback loop, but **is not active in this 10-case demo**.

```python
from telemetry import get_prompt_addendum

# When sufficient data exists (100+ cases), a process engineer can:
addendum = get_prompt_addendum("13.1")
# Returns: "HISTORICAL NOTE: Analysts have overridden 40% of recommendations...
#           COMMON PITFALL: Past analyses missed evidence buried in multi-page docs..."
```

**How it works at scale:**
- After 3+ overrides on a reason code, `get_prompt_addendum()` generates guidance
- A process engineer / data analyst reviews the telemetry dashboard
- They manually inject addendums into prompts or adjust `reason_code_rules.py`
- No automatic LLM retraining — human-in-the-loop for safety

**Why disabled for this exercise:**
- 10 synthetic cases is insufficient for statistically meaningful patterns
- Manual review prevents hallucinated "lessons" from small samples
- Architecture is ready; activation is a post-deployment data ops task

### Viewing Telemetry

```python
from telemetry import get_reason_code_stats, get_all_telemetry_summary, get_case_history

# Per-reason-code breakdown
stats = get_reason_code_stats("13.1")
print(f"Override rate: {stats['override_rate']*100:.0f}%")

# Full summary
summary = get_all_telemetry_summary()
print(f"Total overrides: {summary['total_overrides']}")

# Full audit trail for a case (including admin overwrites)
history = get_case_history("CB-2025-0007")
for entry in history:
    print(f"{entry['timestamp']}: {entry['analyst_override']} ({entry['override_category']})")
```

---

## Post-Ship Improvement Opportunities

The following enhancements were identified during architecture review as **future process optimization opportunities**, not shipping blockers. They are framed for post-deployment iteration once the pilot is live and collecting real analyst telemetry.

### Process Metrics Dashboard
**What:** Throughput (cases/hour), time-to-resolution, queue depth, LLM confidence vs actual override correlation.  
**Why:** Current telemetry dashboard shows *what* happened (overrides, corrections) but not *process efficiency*.  
**Effort:** Low — the telemetry schema in `telemetry.jsonl` already captures timestamps, analyst_id, provider, and confidence. Needs aggregation queries and 2-3 new UI panels. Not built for the 10-case demo because synthetic data produces no meaningful throughput metrics.  
**Risk:** Minimal. Additive, no breaking changes.

### Canonical Reason Code Rules
**What:** Replace simplified scheme rules with a canonical, versioned rule source aligned to an implementation standard (e.g., Meta's implementation standard or equivalent scheme documentation). Real scheme rules include time limits, dollar thresholds, regional exclusions, and regular updates — none of which are in the current simplified rules.  
**Why:** The current `reason_code_rules.py` is deliberately simplified for the exercise. In production, LLM subjectivity on scheme interpretation is unacceptable. A canonical rule source eliminates ambiguity — the LLM's job becomes *evidence extraction*, not *rule interpretation*.  
**Effort:** Medium — requires sourcing canonical rules, encoding them in the same dict structure, and adding version control + update cadence.  
**Risk:** Low. Replaces one rules file with another; no API or UI changes.  
**Note:** This is the highest-impact improvement. It removes the need for prompt experimentation because the rules are unambiguous. The deterministic engine becomes the single source of truth; the LLM only assesses evidence against pre-defined requirements.

### Manager Escalation Queue
**What:** When admin overwrite is blocked (one-time limit exceeded), route to a manager queue instead of a dead end.  
**Why:** Process continuity — currently blocked overwrites require manual Slack/email escalation.  
**Effort:** Low — add queue structure, UI panel, notification hook.  
**Risk:** Minimal. Extends existing admin flow.

### Weekly Process Review Workflow
**What:** Auto-generate override pattern report (reason code, provider, discrepancy type, confidence distribution) for process engineer review every Monday.  
**Why:** Human-in-the-loop feedback loop activation without real-time automation. A process engineer reviews patterns weekly and manually adjusts prompts or rules.  
**Effort:** Medium — report generator + scheduling.  
**Risk:** Low. Read-only, no automated prompt injection.

### Summary Table

| Opportunity | Effort | Risk | Impact on Analyst Workflow | Suggested Priority |
|-------------|--------|------|---------------------------|-------------------|
| Canonical reason code rules | Medium | Low | None (backend only) | **1st** |
| Process metrics dashboard | Low | Minimal | None (admin-only) | 2nd |
| Manager escalation queue | Low | Minimal | None (admin-only) | 3rd |
| Weekly review workflow | Medium | Low | None (read-only) | 4th |

**Key principle:** All improvements are **additive and non-disruptive**. None require changes to the core analyst workflow (case queue → run analysis → review → decide).  
**Activation trigger:** Real analyst telemetry data (20+ live cases) justifies prioritization over synthetic data.

---

## Production Readiness Roadmap

### Short-Term Principles (Next 2–4 Weeks)
- **Canonical reason code rules** — eliminate LLM subjectivity on scheme interpretation
- **OCR quality gate** — detect scanned documents, route appropriately with analyst note
- **Case history UI** — surface telemetry timeline in analyst view for audit transparency
- **Impossibility false-positive review** — weekly review of deterministic overrides to catch edge cases (gift purchases, international AVS)

### Long-Term Principles (Next 2–3 Months)
- **Persistent queue infrastructure** — batch processing survives server restarts
- **Production-grade frontend** — replace Streamlit with a dedicated UI framework
- **SSO integration** — replace password gate with account-bound authentication
- **Model and prompt versioning** — rollback capability for prompt changes
- **Automated regression testing** — synthetic case suite validates prompt/rule changes
- **SOC 2 audit trail** — all decision changes logged with non-repudiation

---

## Environment Variables

See `.env.example` for required variables. You need at least one provider configured.

```bash
KIMI_API_KEY=your_kimi_key
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_claude_key
```

---

## Testing

```bash
# Smoke test
python -c "import json; cases = json.load(open('cases.json')); print(f'{len(cases)} cases loaded')"

# Test page selector
python page_selector.py

# Test analyzer (no API call — checks imports)
python -c "from analyzer import analyze_case; print('OK')"

# Test telemetry
python -c "from telemetry import log_override, get_reason_code_stats, overwrite_decision; print('OK')"

# Test compare script (dev tool)
python compare_two_cases.py --help
```

---

## Resetting Telemetry

`telemetry.jsonl` is append-only and auto-created. To start fresh (e.g., for a demo or test run):

```bash
# Back up first
mv telemetry.jsonl telemetry.jsonl.bak.$(date +%Y%m%d_%H%M%S)

# File is auto-recreated on next decision
```

**Never delete in production** without archiving. The audit trail is required for dispute scheme compliance.

---

## .gitignore

```
telemetry.jsonl
*.pyc
__pycache__/
.env
venv/
*.bak.*
comparison_two_cases.json
```

---

## License

Internal use — Checkout.com case study.
