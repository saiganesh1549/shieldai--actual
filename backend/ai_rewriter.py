"""
ShieldAI — AI Analysis Engine
Powered by OpenAI GPT-4o-mini

How this works (no model training needed):
1. Our crawler collects REAL data from the website (trackers, cookies, forms, policy text)
2. We write a detailed prompt containing that real data + actual regulatory text
3. We send the prompt to OpenAI's GPT-4o-mini via a simple HTTP POST request
4. The AI compares policy claims vs detected behavior and writes its analysis
5. We display the AI's response in the frontend

Why this prevents hallucination:
- The AI can't hallucinate tracker names because WE provide the list of detected trackers
- The AI can't cite fake laws because WE provide the exact regulatory text
- The AI just does the comparison and writes the human-readable analysis
"""

import os
import json
import httpx  # HTTP client for making API calls (like requests but async)
from typing import Optional


# ============================================================
# REGULATORY TEXT — injected into every AI prompt
# This is the "ground truth" that constrains the AI's citations.
# The AI can ONLY cite regulations from this list.
# ============================================================

REGULATIONS = """
GDPR Art. 5(1)(c) — Data Minimization: Personal data shall be adequate, relevant and limited to what is necessary.
GDPR Art. 6(1)(a) — Consent: Processing requires the data subject's consent for specific purposes.
GDPR Art. 7 — Conditions for Consent: Controller must demonstrate consent. Withdrawal must be as easy as giving it.
GDPR Art. 8 — Child's Consent: Processing child's data (under 16) requires parental authorization.
GDPR Art. 13(1)(c) — Legal Basis: Must inform data subject of purposes and legal basis.
GDPR Art. 13(1)(e) — Recipients: Must disclose recipients or categories of recipients.
GDPR Art. 13(2)(a) — Retention: Must state storage period or criteria to determine it.
GDPR Art. 17 — Right to Erasure: Data subject has right to erasure without undue delay.
GDPR Art. 20 — Portability: Right to receive data in structured, machine-readable format.
GDPR Art. 21 — Right to Object: Right to object to processing based on legitimate interest.
GDPR Art. 44-49 — International Transfers: Transfers to third countries need adequate safeguards (SCCs, BCRs).
CCPA §1798.100(b) — Must disclose categories of personal information collected at or before collection.
CCPA §1798.105 — Right to Delete: Must provide at minimum two methods for deletion requests.
CCPA §1798.115 — Must disclose categories of PI sold/shared and categories of third parties.
CCPA §1798.120 — Right to Opt-Out: Consumer can direct business not to sell or share their PI.
CCPA §1798.125 — Non-Discrimination: Cannot discriminate for exercising CCPA rights.
CCPA fines: $2,500/unintentional violation, $7,500/intentional violation. No cap.
ePrivacy Art. 5(3) — Cookie Consent: Storing info on user device requires informed consent except strictly necessary cookies.
COPPA — Must get verifiable parental consent before collecting data from children under 13. Up to $50,120/violation.
"""


# ============================================================
# AI PROVIDER — sends prompts to OpenAI and gets responses
# ============================================================

async def call_ai(system_prompt: str, user_prompt: str) -> Optional[str]:
    """
    Main AI entry point. Sends a system prompt + user prompt to OpenAI.

    Args:
        system_prompt: Instructions for the AI (role, rules, regulations)
        user_prompt: The actual question/task (policy text, scan data, etc.)

    Returns:
        The AI's text response, or None if the call failed
    """
    key = os.getenv("OPENAI_API_KEY", "")
    result = await _call_openai(system_prompt, user_prompt, key)
    if result:
        print("  ✓ AI response via OpenAI")
        return result
    print("  ✗ OpenAI call failed")
    return None


async def _call_openai(system: str, user: str, key: str) -> Optional[str]:
    """
    Makes the actual HTTP POST request to OpenAI's chat completions API.

    Uses gpt-4o-mini because it's:
    - Fast (< 3 second responses)
    - Cheap ($0.15 per 1M input tokens)
    - Good enough for compliance analysis
    - Temperature 0.2 keeps it factual (low creativity = fewer hallucinations)
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",      # API key for authentication
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",                # Model selection
                    "messages": [
                        {"role": "system", "content": system},  # Instructions/role
                        {"role": "user", "content": user},      # The actual task
                    ],
                    "temperature": 0.2,   # Low = factual, high = creative
                    "max_tokens": 4000,   # Max response length
                },
            )
            data = resp.json()
            # Extract the AI's response text from the API response structure
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            # If the response doesn't have "choices", something went wrong (quota, auth, etc.)
            print(f"  OpenAI error response: {str(data)[:400]}")
            return None
    except Exception as e:
        print(f"  OpenAI exception: {e}")
        return None


# ============================================================
# POLICY ANALYSIS — AI grades each section of the privacy policy
# ============================================================

async def analyze_policy_with_ai(policy_text: str, crawl_data: dict) -> list:
    """
    Sends the privacy policy text + detected website behavior to GPT.
    GPT grades each policy section (red/yellow/green) and cites specific regulations.

    The key insight: we provide BOTH what the policy says AND what we detected,
    so the AI can identify contradictions between claims and reality.

    Returns: List of dicts with title, grade, text, and regulation citations
    """

    # Extract detected evidence from crawl data to include in the prompt
    trackers = crawl_data.get("trackers_found", [])
    tracker_list = ", ".join(t["name"] for t in trackers) or "none detected"

    signals = crawl_data.get("data_collection_signals", [])
    signal_list = ", ".join(s["description"] for s in signals) or "none detected"

    consent = crawl_data.get("consent_banner", {})
    consent_issues = "; ".join(consent.get("issues", [])) or "none"

    # Collect all form field names (e.g., "email", "phone", "address")
    form_fields = []
    for f in crawl_data.get("forms_detected", []):
        for field in f.get("fields", []):
            form_fields.append(field["name"])
    form_list = ", ".join(form_fields[:15]) or "none detected"

    # System prompt: tells the AI its role and constraints
    system = f"""You are a privacy compliance auditor. You ONLY cite regulations from this list:
{REGULATIONS}

You NEVER invent regulation articles. You base analysis ONLY on the evidence provided.
Do NOT assume or infer data practices not in the evidence.
If policy text is empty or not available, note that you cannot fully assess compliance."""

    # User prompt: provides the actual data to analyze
    user = f"""Analyze this privacy policy against detected website behavior:

DETECTED TRACKERS: {tracker_list}
DETECTED DATA COLLECTION: {signal_list}
DETECTED FORM FIELDS: {form_list}
COOKIE CONSENT ISSUES: {consent_issues}

PRIVACY POLICY TEXT:
{policy_text[:6000]}

Grade each section. Return a JSON array where each item has:
- "title": section name
- "grade": "red" (non-compliant), "yellow" (partial), or "green" (compliant)
- "text": 1-2 sentences referencing specific detected evidence vs policy claims
- "regs": array of regulation citations from the list above

Cover: Data Collection, Third-Party Sharing, Legal Basis, Cookie/Consent, User Rights, Data Retention, Contact Info.
Return ONLY valid JSON array, no markdown fences."""

    # Send to OpenAI and parse the JSON response
    response = await call_ai(system, user)
    if response:
        try:
            # Clean any markdown code fences the AI might add (```json ... ```)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            parsed = json.loads(cleaned.strip())
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception as e:
            print(f"  JSON parse error: {e}")

    # Fallback: if AI is unavailable, build analysis from crawl data directly
    return _build_analysis_from_crawl(crawl_data)


def _build_analysis_from_crawl(crawl_data: dict) -> list:
    """
    Factual fallback when AI is unavailable.
    Only reports what we actually detected — no guessing, no assumptions.
    This ensures the app still works even if the OpenAI API is down.
    """
    trackers = crawl_data.get("trackers_found", [])
    ad_trackers = [t for t in trackers if t.get("category") == "advertising"]
    consent = crawl_data.get("consent_banner", {})
    policy = crawl_data.get("privacy_policy_text", "").lower()
    has_policy = len(policy) > 200  # Did we get enough text to analyze?
    clauses = []

    # Check: are detected trackers named in the policy?
    if trackers:
        disclosed = sum(1 for t in trackers if t["name"].lower().split()[0] in policy) if has_policy else 0
        clauses.append({
            "title": "Third-Party Data Sharing",
            "grade": "red" if ad_trackers and disclosed < len(ad_trackers) else "yellow" if trackers else "green",
            "text": f"Detected {len(trackers)} trackers ({len(ad_trackers)} advertising). {'Policy names ' + str(disclosed) + ' of them.' if has_policy else 'Could not verify — policy not retrieved.'}",
            "regs": ["CCPA §1798.115", "GDPR Art. 13(1)(e)"]
        })

    # Check: are there cookie consent issues?
    issues = consent.get("issues", [])
    if issues:
        clauses.append({
            "title": "Cookie & Consent Compliance",
            "grade": "red" if len(issues) >= 2 else "yellow",
            "text": "; ".join(issues) + ".",
            "regs": ["ePrivacy Art. 5(3)", "GDPR Art. 7"]
        })

    # If we have the policy text, check for user rights and retention
    if has_policy:
        # Count how many of 7 key user rights are mentioned
        rights_found = sum(1 for kw in ["access", "deletion", "erasure", "portability", "object", "opt out", "do not sell"] if kw in policy)
        clauses.append({
            "title": "User Rights Disclosure",
            "grade": "green" if rights_found >= 4 else "yellow" if rights_found >= 2 else "red",
            "text": f"Policy mentions {rights_found} of 7 key user rights.",
            "regs": ["GDPR Art. 15-21", "CCPA §1798.100-125"]
        })

        # Check for specific retention periods (not just "as long as necessary")
        has_retention = any(w in policy for w in ["retention period", "retain for", "stored for", "deleted after", "days", "months", "years"])
        clauses.append({
            "title": "Data Retention Policy",
            "grade": "green" if has_retention else "red",
            "text": "Specific retention periods found." if has_retention else "No specific retention periods found.",
            "regs": ["GDPR Art. 13(2)(a)"]
        })

    return clauses


# ============================================================
# POLICY REWRITER — AI generates compliant replacement clauses
# ============================================================

async def rewrite_policy_clauses(gaps: list, crawl_data: dict) -> list:
    """
    For each compliance gap, asks GPT to write a legally compliant replacement clause.

    The AI sees:
    - What the current policy says (or doesn't say)
    - What was actually detected on the website
    - Which regulations apply
    And writes a specific, compliant clause that names actual trackers and data types.

    Limited to 5 rewrites to save API costs.
    """
    trackers = crawl_data.get("trackers_found", [])
    tracker_list = ", ".join(t["name"] for t in trackers) or "none"
    rewrite_items = []

    for i, gap in enumerate(gaps):
        if i >= 5:  # Cap at 5 rewrites to control API usage
            break

        # System prompt constrains the AI to only use real evidence
        system = f"""You are a privacy policy writer. Write clear, legally compliant replacement clauses.
RULES:
1. ONLY reference data practices from the DETECTED EVIDENCE
2. ONLY cite regulations from: {REGULATIONS}
3. Write in plain language. Be specific — name actual trackers and data types.
4. Write 3-6 sentences as a paragraph."""

        # User prompt provides the specific gap to fix
        user = f"""Write a replacement clause for this gap:
GAP: {gap['title']}
REGULATION: {gap['regulation']}
CURRENT POLICY: {gap['claim']}
DETECTED BEHAVIOR: {gap['actual']}
TRACKERS ON SITE: {tracker_list}
Write ONLY the replacement clause text."""

        response = await call_ai(system, user)
        rewrite_items.append({
            "label": gap["title"],
            "gap_fixed": gap["title"][:60],
            "regulation": gap["regulation"],
            "old": gap["claim"],          # What the policy currently says
            "new": response.strip() if response else f"[AI unavailable] Update policy to address {gap['title']} per {gap['regulation']}.",
        })

    return rewrite_items


# ============================================================
# CHAT — Interactive AI Privacy Advisor
# ============================================================

async def chat_with_agent(message: str, scan_context: dict) -> str:
    """
    Powers the AI chat feature. Users can ask questions like:
    - "What should I fix first?"
    - "Explain the cookie consent issue"
    - "Am I GDPR compliant?"
    - "What is CCPA?"

    The AI sees the current scan results so it can give specific,
    contextual answers — not generic advice.
    """
    # Extract scan results to inject into the AI's context
    trackers = scan_context.get("trackers_found", [])
    gaps = scan_context.get("gaps", [])
    score = scan_context.get("overall_score", "unknown")
    company = scan_context.get("company", "the scanned website")

    # System prompt gives the AI its identity and the scan context
    system = f"""You are ShieldAI — an AI privacy compliance advisor. You just completed a scan of {company}.

SCAN RESULTS:
- Compliance Score: {score}%
- Trackers Found: {', '.join(t['name'] for t in trackers) if trackers else 'none'}
- Gaps: {'; '.join(g['title'] + ' (' + g['severity'] + ', ' + g['fine'] + ')' for g in gaps) if gaps else 'none'}

REGULATIONS YOU KNOW:
{REGULATIONS}

RULES:
- You are a friendly, expert privacy advisor — like talking to a privacy lawyer
- Answer based on the ACTUAL scan results above
- Give practical, actionable advice
- Cite specific regulations when relevant
- Keep answers concise (2-4 sentences) unless they ask for detail
- If they ask about something not in the scan, be honest about limitations
- You can discuss general privacy law questions too"""

    # The user's message goes straight through — the system prompt provides context
    response = await call_ai(system, message)
    return response or "I'm having trouble connecting to my AI backend right now. Please try again in a moment."


# ============================================================
# ROADMAP GENERATOR — creates a prioritized remediation plan
# ============================================================

def generate_roadmap(gaps: list) -> list:
    """
    Converts compliance gaps into an actionable remediation roadmap.
    Sorts by financial risk (highest first) and estimates fix time.

    This is entirely deterministic — no AI needed.
    Each gap gets a priority number, time estimate, and potential savings.
    """
    roadmap = []
    # Sort gaps by fine amount (biggest risk first = highest priority)
    sorted_gaps = sorted(gaps, key=lambda g: g.get("fine_raw", 0), reverse=True)

    # Estimated fix times by category (based on industry standards)
    time_map = {
        "cookie": "2-4 hours", "consent": "2-4 hours",
        "tracker": "4-8 hours", "advertising": "4-8 hours", "analytics": "2-4 hours",
        "location": "1-2 hours", "retention": "1-3 days",
        "deletion": "1-2 weeks", "erasure": "1-2 weeks",
        "excessive": "2-4 hours", "minimization": "2-4 hours",
        "children": "1-2 days", "cross-border": "2-3 days", "transfer": "2-3 days",
        "right": "1-2 weeks", "recording": "2-4 hours", "session": "2-4 hours",
    }

    for i, gap in enumerate(sorted_gaps):
        # Match gap title to a time estimate
        title_lower = gap["title"].lower()
        time = "1-2 weeks"  # Default
        for keyword, t in time_map.items():
            if keyword in title_lower:
                time = t
                break

        roadmap.append({
            "priority": i + 1,
            "title": f"Fix: {gap['title']}",
            "description": f"Address this {gap['severity']} finding to comply with {gap['regulation'].split('·')[0].strip()}.",
            "savings": gap["fine"],    # How much risk this fix eliminates
            "time": time,              # Estimated implementation time
            "regulation": gap["regulation"].split("·")[0].strip(),
        })

    return roadmap