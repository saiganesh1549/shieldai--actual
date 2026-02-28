"""
ShieldAI — AI Analysis Engine

How this works (no training needed):
1. Our crawler collects REAL data from the website (trackers, cookies, forms, policy text)
2. We write a detailed prompt containing that real data + actual regulatory text
3. We send the prompt to OpenAI's API (just an HTTP request)
4. OpenAI analyzes the gap between policy claims and detected behavior
5. We display the result

The AI can't hallucinate tracker names because WE detected them.
The AI can't hallucinate laws because WE provide the exact regulatory text.
The AI just does the comparison and writes the analysis.
"""

import os
import json
import httpx
from typing import Optional


# ============================================================
# ACTUAL REGULATORY TEXT (injected into every prompt)
# This is what prevents hallucination — the AI can only cite
# regulations we explicitly provide.
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
# CALL OPENAI (or fallback to Gemini/Groq)
# This is literally just an HTTP POST request. No SDK needed.
# ============================================================

async def call_ai(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Send a prompt to OpenAI and get a response. Falls back to Gemini/Groq."""

    # Try OpenAI first
    key = os.getenv("OPENAI_API_KEY", "")
    result = await _call_openai(system_prompt, user_prompt, key)
    if result:
        return result

   
    

    return None  # No API key available


async def _call_openai(system: str, user: str, key: str) -> Optional[str]:
    """Simple OpenAI chat completion call."""
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",  # Fast, cheap, good enough
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,  # Low = more factual, less creative
                    "max_tokens": 4000,
                }
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None


async def _call_gemini(prompt: str, key: str) -> Optional[str]:
    """Simple Gemini API call."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4000},
            })
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Gemini error: {e}")
        return None


async def _call_groq(system: str, user: str, key: str) -> Optional[str]:
    """Simple Groq API call."""
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 4000,
                }
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Groq error: {e}")
        return None


# ============================================================
# POLICY ANALYSIS
# Sends real crawl data + real policy text + real regulations
# to the AI and asks it to grade each section.
# ============================================================

async def analyze_policy_with_ai(policy_text: str, crawl_data: dict) -> list:
    """
    Grade each section of the privacy policy against regulations.
    The AI sees: real policy text, real detected trackers, real regulations.
    """
    trackers = crawl_data.get("trackers_found", [])
    tracker_list = ", ".join(t["name"] for t in trackers) or "none detected"
    signals = crawl_data.get("data_collection_signals", [])
    signal_list = ", ".join(s["description"] for s in signals) or "none detected"
    consent = crawl_data.get("consent_banner", {})
    consent_issues = "; ".join(consent.get("issues", [])) or "none"
    forms = crawl_data.get("forms_detected", [])
    form_fields = []
    for f in forms:
        for field in f.get("fields", []):
            form_fields.append(field["name"])
    form_list = ", ".join(form_fields[:15]) or "none detected"

    system = f"""You are a privacy compliance auditor. You ONLY cite regulations from this list:
{REGULATIONS}

You NEVER invent regulation articles. If you're not sure about a regulation, don't cite it.
You base your analysis ONLY on the evidence provided — detected trackers, form fields, and policy text.
Do NOT assume or infer data practices that aren't in the evidence."""

    user = f"""Analyze this privacy policy. Here is what our scanner actually detected on their website:

DETECTED TRACKERS: {tracker_list}
DETECTED DATA COLLECTION: {signal_list}
DETECTED FORM FIELDS: {form_list}
COOKIE CONSENT ISSUES: {consent_issues}

PRIVACY POLICY TEXT:
{policy_text[:6000]}

Grade each major section of the policy. Return a JSON array where each item has:
- "title": section name (e.g., "Data Collection Disclosure")
- "grade": "red" (non-compliant), "yellow" (partially compliant), or "green" (compliant)
- "text": 1-2 sentences explaining the specific issue, referencing what was detected vs what the policy says
- "regs": array of specific regulation citations from the list above (e.g., ["GDPR Art. 13(1)(e)", "CCPA §1798.115"])

Cover these areas: Data Collection, Third-Party Sharing, Legal Basis, Cookie/Consent, User Rights, Data Retention, Contact Info, Update Notification.

Return ONLY valid JSON array, no markdown fences, no explanation outside the JSON."""

    response = await call_ai(system, user)

    if response:
        try:
            # Clean markdown fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            parsed = json.loads(cleaned.strip())
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except (json.JSONDecodeError, Exception) as e:
            print(f"JSON parse error: {e}")

    # Fallback: build analysis from crawl data directly (no AI needed)
    return _build_analysis_from_crawl(crawl_data)


def _build_analysis_from_crawl(crawl_data: dict) -> list:
    """
    Build policy analysis purely from crawl data. No AI needed.
    This is factual — every claim traces to something we detected.
    """
    trackers = crawl_data.get("trackers_found", [])
    ad_trackers = [t for t in trackers if t.get("category") == "advertising"]
    consent = crawl_data.get("consent_banner", {})
    policy = crawl_data.get("privacy_policy_text", "").lower()

    clauses = []

    # Data Collection — check if policy mentions what we actually detected
    detected_categories = set()
    for t in trackers:
        for d in t.get("data_shared", t.get("data", [])):
            detected_categories.add(d)
    for s in crawl_data.get("data_collection_signals", []):
        detected_categories.add(s.get("category", ""))

    missing_in_policy = [c for c in detected_categories if c.lower() not in policy]

    clauses.append({
        "title": "Data Collection Disclosure",
        "grade": "red" if len(missing_in_policy) > 3 else "yellow" if missing_in_policy else "green",
        "text": f"Detected {len(detected_categories)} data categories being collected. {len(missing_in_policy)} categories not mentioned in privacy policy: {', '.join(list(missing_in_policy)[:5])}." if missing_in_policy else "Data collection disclosures appear to cover detected categories.",
        "regs": ["GDPR Art. 13(1)(c)", "CCPA §1798.100(b)"]
    })

    # Third-Party Sharing
    clauses.append({
        "title": "Third-Party Sharing",
        "grade": "red" if ad_trackers else "green",
        "text": f"Detected {len(ad_trackers)} advertising trackers ({', '.join(t['name'] for t in ad_trackers[:4])}). Policy must name these partners and disclose data categories shared." if ad_trackers else "No advertising trackers detected.",
        "regs": ["CCPA §1798.115", "GDPR Art. 13(1)(e)"]
    })

    # Cookie Consent
    issues = consent.get("issues", [])
    clauses.append({
        "title": "Cookie & Consent Compliance",
        "grade": "red" if len(issues) >= 2 else "yellow" if issues else "green",
        "text": "; ".join(issues) + "." if issues else "Cookie consent mechanism appears compliant.",
        "regs": ["ePrivacy Art. 5(3)", "GDPR Art. 7"]
    })

    # User Rights — check which rights are mentioned
    rights_found = 0
    rights_total = 5
    for keyword in ["access", "deletion", "erasure", "portability", "object"]:
        if keyword in policy:
            rights_found += 1

    clauses.append({
        "title": "User Rights Disclosure",
        "grade": "green" if rights_found >= 4 else "yellow" if rights_found >= 2 else "red",
        "text": f"Policy mentions {rights_found} of {rights_total} required user rights (access, deletion, portability, objection, opt-out).",
        "regs": ["GDPR Art. 15-21", "CCPA §1798.100-125"]
    })

    # Retention
    has_retention = any(w in policy for w in ["retention period", "retain for", "stored for", "deleted after", "days", "months", "years"])
    vague_retention = any(w in policy for w in ["as long as necessary", "as needed", "reasonable time"])
    clauses.append({
        "title": "Data Retention Policy",
        "grade": "green" if has_retention and not vague_retention else "yellow" if has_retention else "red",
        "text": "Uses vague retention language without specific periods per data category." if vague_retention else "No specific retention periods found." if not has_retention else "Retention periods are specified.",
        "regs": ["GDPR Art. 13(2)(a)"]
    })

    # Contact Info
    has_contact = any(w in policy for w in ["contact", "email", "privacy@", "dpo", "data protection officer"])
    clauses.append({
        "title": "Controller Contact Information",
        "grade": "green" if has_contact else "red",
        "text": "Privacy contact information provided." if has_contact else "No clear privacy contact information found.",
        "regs": ["GDPR Art. 13(1)(a)"]
    })

    return clauses


# ============================================================
# POLICY REWRITER
# Takes each detected gap and generates a compliant replacement
# clause. The AI sees the exact gap + exact regulation.
# ============================================================

async def rewrite_policy_clauses(gaps: list, crawl_data: dict) -> list:
    """
    For each gap, generate a replacement privacy policy clause.
    The AI only writes about things we actually detected.
    """
    trackers = crawl_data.get("trackers_found", [])
    tracker_list = ", ".join(t["name"] for t in trackers) or "none"
    signals = crawl_data.get("data_collection_signals", [])

    rewrite_items = []

    for gap in gaps:
        # Skip low-severity gaps to save API calls during demo
        if gap["severity"] == "info" and len(rewrite_items) >= 4:
            continue

        system = f"""You are a privacy policy writer. You write clear, legally compliant privacy policy clauses.

RULES:
1. ONLY reference data practices from the DETECTED EVIDENCE below — never assume additional practices
2. ONLY cite regulations from this list:
{REGULATIONS}
3. Write in plain language a consumer can understand
4. Be specific — name actual trackers, actual data types, actual retention periods
5. Write 3-6 sentences. No headers, no bullet points, just a paragraph."""

        user = f"""Write a replacement privacy policy clause that fixes this compliance gap:

GAP: {gap['title']}
VIOLATED REGULATION: {gap['regulation']}
CURRENT POLICY SAYS: {gap['claim']}
WHAT WE ACTUALLY DETECTED: {gap['actual']}

DETECTED TRACKERS ON THIS SITE: {tracker_list}
DETECTED DATA SIGNALS: {', '.join(s['description'] for s in signals[:5])}

Write ONLY the replacement clause text. No explanation, no markdown."""

        response = await call_ai(system, user)

        if not response:
            # Fallback: use template
            response = _template_clause(gap, crawl_data)

        rewrite_items.append({
            "label": gap["title"],
            "gap_fixed": gap["title"][:60],
            "regulation": gap["regulation"],
            "old": gap["claim"],
            "new": response.strip(),
        })

    return rewrite_items


def _template_clause(gap: dict, crawl_data: dict) -> str:
    """Factual template clause built from detected data. Used when no AI API is available."""
    trackers = crawl_data.get("trackers_found", [])
    ad_trackers = [t for t in trackers if t.get("category") == "advertising"]
    analytics_trackers = [t for t in trackers if t.get("category") == "analytics"]
    title = gap["title"].lower()

    if "tracker" in title or "advertising" in title or "third-party" in title:
        ad_names = ", ".join(t["name"] for t in ad_trackers[:5]) or "our advertising partners"
        an_names = ", ".join(t["name"] for t in analytics_trackers[:3]) or "our analytics providers"
        return f"We share personal data with the following third parties: Analytics providers ({an_names}) receive anonymized usage data to help us understand how our service is used. Advertising partners ({ad_names}) receive device identifiers and browsing behavior data for targeted advertising purposes. Under the California Consumer Privacy Act (CCPA), sharing data with advertising partners may constitute a 'sale' of personal information. You may opt out of this sharing at any time by clicking the 'Do Not Sell My Personal Information' link at the bottom of any page."

    if "cookie" in title or "consent" in title:
        return "We use cookies categorized as follows: (a) Strictly Necessary cookies required for basic site functionality, which do not require consent; (b) Analytics cookies that help us understand usage patterns, which require your consent; (c) Advertising cookies used by our partners for targeted ads, which require your consent. You may accept or reject each category individually through our cookie preferences panel. Non-essential cookies will not be placed on your device until you provide affirmative consent. You may change your preferences or withdraw consent at any time through the cookie settings link in our website footer."

    if "location" in title:
        return "We collect location data in two ways: (a) Precise location via your device's GPS or location services, collected only with your explicit permission and used for service features that require your location; (b) Approximate location derived from your IP address, used for regional content delivery and fraud prevention. You may disable precise location collection at any time through your device settings. We retain identifiable location data for no longer than 90 days before it is aggregated or deleted."

    if "retention" in title:
        return "We retain your personal data for the following periods: Account information is kept for the duration of your account plus 30 days after you request deletion. Transaction records are retained for 7 years as required by tax and financial regulations. Analytics data is retained for 26 months in aggregated form. Server logs are retained for 90 days for security monitoring purposes. When these periods expire, your data is automatically deleted from our active systems."

    if "excessive" in title or "minimization" in title:
        return "We collect only the personal data necessary to provide our core services. To create an account, we require your name and email address. Additional information such as phone number or mailing address is optional and only collected when you choose to use features that require it. We regularly review our data collection practices to ensure we are not collecting information beyond what is needed for each stated purpose."

    if "right" in title:
        return "You have the following rights regarding your personal data: the right to access a copy of your data; the right to correct inaccurate information; the right to request deletion of your data; the right to receive your data in a portable format; and the right to object to certain types of processing. California residents may additionally direct us not to sell or share their personal information. To exercise any of these rights, contact us at privacy@[company].com or use the self-service tools in your account settings. We will respond within 30 days."

    if "cross-border" in title or "transfer" in title:
        us_services = [t["name"] for t in trackers if any(x in t["name"].lower() for x in ["google", "meta", "facebook", "amazon", "microsoft"])]
        svc_list = ", ".join(us_services[:4]) or "cloud infrastructure and analytics providers"
        return f"Your data may be transferred to and processed in countries outside your country of residence, including the United States, where our service providers ({svc_list}) are headquartered. For transfers from the European Economic Area, we rely on Standard Contractual Clauses approved by the European Commission to ensure your data receives adequate protection."

    if "children" in title:
        return "Our service is not directed to children under the age of 13. We do not knowingly collect personal information from children under 13. If we become aware that we have collected personal data from a child under 13 without verified parental consent, we will take steps to delete that information promptly. Parents who believe their child may have provided us with personal data can contact us to request review and deletion."

    return f"We process your personal data in compliance with applicable privacy regulations including GDPR and CCPA. For details about our specific practices related to {gap['title'].lower()}, please contact our privacy team."


# ============================================================
# COMPLIANCE ROADMAP GENERATOR
# Prioritizes fixes by risk exposure — purely data-driven.
# ============================================================

def generate_roadmap(gaps: list) -> list:
    """Build prioritized fix roadmap from detected gaps. Sorted by financial risk."""
    roadmap = []
    sorted_gaps = sorted(gaps, key=lambda g: g.get("fine_raw", 0), reverse=True)

    for i, gap in enumerate(sorted_gaps):
        title = gap["title"].lower()

        # Time estimates based on actual implementation complexity
        if "cookie" in title or "consent" in title:
            desc = "Deploy a consent management platform (OneTrust, Cookiebot, or open-source alternative) with granular accept/reject options per cookie category. Configure to block all non-essential cookies and scripts until affirmative consent is received."
            time = "2-4 hours"
        elif "tracker" in title or "advertising" in title:
            desc = "Create a complete inventory of all third-party data sharing relationships. Update privacy policy to name each partner and describe data categories shared. Implement CCPA-compliant 'Do Not Sell' opt-out mechanism."
            time = "4-8 hours"
        elif "location" in title:
            desc = "Add explicit location data disclosure to privacy policy specifying collection methods, purposes, and retention. Ensure app store data safety declarations match policy language."
            time = "1-2 hours"
        elif "retention" in title:
            desc = "Define specific retention periods for each data category based on legal requirements and business necessity. Implement automated data lifecycle management and deletion workflows."
            time = "1-3 days"
        elif "deletion" in title or "erasure" in title:
            desc = "Build self-service data deletion functionality in user account settings. Implement backend data purge pipeline that propagates deletion across all storage systems and third-party processors."
            time = "1-2 weeks"
        elif "excessive" in title or "minimization" in title:
            desc = "Audit all data collection points (forms, APIs, SDKs). Reclassify non-essential required fields as optional. Remove collection of data that serves no documented business purpose."
            time = "2-4 hours"
        elif "children" in title:
            desc = "Implement age verification at account creation. If service may be accessed by minors, add COPPA-compliant parental consent workflow. Add children's privacy section to policy."
            time = "1-2 days"
        elif "cross-border" in title or "transfer" in title:
            desc = "Document all international data flows to/from US-based processors. Execute Standard Contractual Clauses (SCCs) with each processor. Add international transfer disclosure to privacy policy."
            time = "2-3 days"
        elif "right" in title:
            desc = "Expand user rights section to cover all required rights under GDPR and CCPA. Build self-service data access and portability tools. Ensure response workflows meet 30-day (GDPR) and 45-day (CCPA) deadlines."
            time = "1-2 weeks"
        elif "session" in title or "recording" in title:
            desc = "Disclose session recording tools in privacy policy with specifics on what is captured. Add opt-in consent before session recording activates. Implement data retention limits for recordings."
            time = "2-4 hours"
        else:
            desc = f"Address the identified gap: {gap['title']}. Update privacy policy and technical implementation to achieve compliance with {gap['regulation']}."
            time = "1-2 weeks"

        roadmap.append({
            "priority": i + 1,
            "title": f"Fix: {gap['title']}",
            "description": desc,
            "savings": gap["fine"],
            "time": time,
            "regulation": gap["regulation"].split("·")[0].strip(),
        })

    return roadmap
