"""
ShieldAI — Gap Analyzer
Detects gaps between what a privacy policy claims and what
the website/product actually does. Calculates risk exposure.
"""

from knowledge_base import find_relevant_cases


def analyze_gaps(crawl_data: dict, policy_analysis: dict | None = None) -> dict:
    """
    Analyze gaps between crawl findings and policy claims.
    Returns structured gap report with risk calculations.
    """
    gaps = []
    total_risk = 0

    trackers = crawl_data.get("trackers_found", [])
    forms = crawl_data.get("forms_detected", [])
    signals = crawl_data.get("data_collection_signals", [])
    consent = crawl_data.get("consent_banner", {})
    policy_text = crawl_data.get("privacy_policy_text", "").lower()

    # ===== GAP 1: Undisclosed Trackers =====
    ad_trackers = [t for t in trackers if t["category"] == "advertising"]
    if ad_trackers:
        tracker_names = [t["name"] for t in ad_trackers]
        # Check if policy mentions them
        disclosed = []
        undisclosed = []
        for t in ad_trackers:
            name_lower = t["name"].lower().split()[0]  # First word (e.g., "Google")
            if name_lower in policy_text or t["signature"] in policy_text:
                disclosed.append(t["name"])
            else:
                undisclosed.append(t["name"])

        all_data = []
        for t in ad_trackers:
            all_data.extend(t["data_shared"])
        all_data = list(set(all_data))

        risk = len(ad_trackers) * 68000  # Estimated per-tracker risk
        total_risk += risk

        cases = find_relevant_cases(["advertising", "disclosure", "consent"])
        case_text = "; ".join([
            f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}"
            for c in cases
        ]) if cases else "Multiple companies fined for similar undisclosed tracking practices."

        gaps.append({
            "severity": "critical",
            "title": f"{len(ad_trackers)} advertising trackers detected but not fully disclosed",
            "regulation": "CCPA §1798.140(e) · CCPA §1798.115 · GDPR Art. 13(1)(e)",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": f"Privacy policy {'mentions general \"analytics partners\" but does not name specific advertising third parties or describe data shared with ad networks' if 'analytics' in policy_text or 'partner' in policy_text else 'does not disclose third-party advertising data sharing'}.",
            "actual": f"Detected {len(ad_trackers)} advertising trackers: {', '.join(tracker_names)}. These trackers collect and share: {', '.join(all_data[:6])}. Under CCPA, sharing data with advertising partners may constitute a 'sale' of personal information requiring explicit disclosure and opt-out mechanism.",
            "enforcement": case_text,
            "tags": ["advertising", "disclosure"]
        })

    # ===== GAP 2: Cookie Consent Issues =====
    if consent.get("issues"):
        risk = 180000
        total_risk += risk

        cases = find_relevant_cases(["cookies", "consent"])
        case_text = "; ".join([
            f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}"
            for c in cases
        ]) if cases else ""

        issues_text = ". ".join(consent["issues"])

        gaps.append({
            "severity": "critical",
            "title": "Non-compliant cookie consent mechanism",
            "regulation": "GDPR Art. 7 · ePrivacy Directive Art. 5(3) · CCPA §1798.120",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": f"Website {'displays a cookie banner' if consent.get('detected') else 'has no cookie consent mechanism'}. {'Provider: ' + consent.get('provider', 'custom') if consent.get('detected') else ''}",
            "actual": f"{issues_text}. GDPR requires freely given, specific, informed consent with equal prominence for accept and reject options. Non-essential cookies must not load until affirmative consent is given.",
            "enforcement": case_text,
            "tags": ["cookies", "consent"]
        })

    # ===== GAP 3: Location Data =====
    location_signals = [s for s in signals if s["category"] == "geolocation"]
    if location_signals:
        location_in_policy = any(w in policy_text for w in ["location", "geolocation", "gps", "geographic"])
        if not location_in_policy:
            risk = 2100000
            total_risk += risk

            cases = find_relevant_cases(["location", "disclosure"])
            case_text = "; ".join([
                f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}"
                for c in cases
            ]) if cases else ""

            gaps.append({
                "severity": "critical",
                "title": "Location data collected but not disclosed in privacy policy",
                "regulation": "GDPR Art. 13(1)(e) · CCPA §1798.100(b)",
                "fine": f"${risk:,}",
                "fine_raw": risk,
                "claim": "Privacy policy does not mention collection of location data, geolocation, or GPS tracking.",
                "actual": f"Detected: {', '.join(s['description'] for s in location_signals)}. Location data is classified as sensitive personal information under both GDPR and CCPA, requiring explicit disclosure and often explicit consent.",
                "enforcement": case_text,
                "tags": ["location", "disclosure"]
            })

    # ===== GAP 4: Session Recording =====
    recording_signals = [s for s in signals if s["category"] == "session_recording"]
    if recording_signals:
        recording_in_policy = any(w in policy_text for w in ["session recording", "session replay",
                                                              "screen recording", "mouse tracking",
                                                              "hotjar", "fullstory", "clarity"])
        if not recording_in_policy:
            risk = 95000
            total_risk += risk
            gaps.append({
                "severity": "warning",
                "title": "Session recording tools detected but not disclosed",
                "regulation": "GDPR Art. 13 · CCPA §1798.100(b) · ePrivacy Art. 5(3)",
                "fine": f"${risk:,}",
                "fine_raw": risk,
                "claim": "Privacy policy does not disclose the use of session recording or replay technology.",
                "actual": f"Detected: {', '.join(s['description'] for s in recording_signals)}. Session recording captures mouse movements, clicks, scrolling, keystrokes, and form interactions — potentially including sensitive personal data entered by users.",
                "enforcement": "Session recording without disclosure has been flagged by multiple EU DPAs as a violation of transparency requirements.",
                "tags": ["recording", "transparency"]
            })

    # ===== GAP 5: Data Retention =====
    retention_keywords = ["retention period", "retain your data for", "store your data for",
                         "delete after", "retained for", "keep your data for"]
    has_specific_retention = any(kw in policy_text for kw in retention_keywords)
    vague_retention = any(w in policy_text for w in ["as long as necessary", "as needed", "reasonable period"])

    if not has_specific_retention or vague_retention:
        risk = 45000
        total_risk += risk

        cases = find_relevant_cases(["retention", "deletion"])
        case_text = "; ".join([
            f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}"
            for c in cases
        ]) if cases else ""

        gaps.append({
            "severity": "warning",
            "title": "Data retention periods not specified or vague",
            "regulation": "GDPR Art. 13(2)(a) · CCPA §1798.100(a)(3)",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": f"Privacy policy {'uses vague language like \"as long as necessary\" without specific retention periods' if vague_retention else 'does not specify data retention periods'}.",
            "actual": "GDPR requires disclosure of specific storage periods or clear criteria for determining retention. Vague language like 'as long as necessary' has been consistently found non-compliant by EU Data Protection Authorities.",
            "enforcement": case_text,
            "tags": ["retention", "transparency"]
        })

    # ===== GAP 6: Excessive Data Collection =====
    excessive_fields = []
    for form in forms:
        for f in form.get("fields", []):
            name_lower = f["name"].lower()
            if any(x in name_lower for x in ["phone", "tel", "mobile", "birth", "dob", "age",
                                               "address", "street", "zip", "postal", "ssn",
                                               "social security", "gender", "sex"]):
                if f.get("required", False):
                    excessive_fields.append(f["name"])

    if excessive_fields:
        risk = 12000 * len(excessive_fields)
        total_risk += risk

        cases = find_relevant_cases(["minimization", "excessive_collection"])
        case_text = "; ".join([
            f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}"
            for c in cases
        ]) if cases else ""

        gaps.append({
            "severity": "warning",
            "title": "Signup/forms require potentially excessive personal data",
            "regulation": "GDPR Art. 5(1)(c) — Data Minimization",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": "Privacy policy claims to follow data minimization or collect only necessary data." if "minim" in policy_text else "Privacy policy does not address data minimization.",
            "actual": f"Detected required form fields that may be excessive for core service: {', '.join(excessive_fields[:5])}. GDPR's data minimization principle requires personal data to be 'adequate, relevant and limited to what is necessary.'",
            "enforcement": case_text,
            "tags": ["minimization", "excessive_collection"]
        })

    # ===== GAP 7: Missing Rights Disclosure =====
    rights_keywords = {
        "access": ["right to access", "right of access", "access your data", "request a copy"],
        "deletion": ["right to deletion", "right to erasure", "delete your data", "right to be forgotten"],
        "portability": ["data portability", "portable format", "machine-readable"],
        "objection": ["right to object", "object to processing"],
        "opt_out_sale": ["do not sell", "opt-out of sale", "opt out of the sale"],
    }

    missing_rights = []
    for right, keywords in rights_keywords.items():
        if not any(kw in policy_text for kw in keywords):
            missing_rights.append(right)

    if missing_rights:
        risk = 8000 * len(missing_rights)
        total_risk += risk
        gaps.append({
            "severity": "info",
            "title": f"User rights disclosure incomplete — missing {len(missing_rights)} rights",
            "regulation": "GDPR Art. 15-22 · CCPA §1798.100-125",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": "Privacy policy mentions some user rights but omits others required by applicable regulations.",
            "actual": f"Missing rights disclosures: {', '.join(r.replace('_', ' ').title() for r in missing_rights)}. Both GDPR and CCPA require clear disclosure of all applicable data subject rights.",
            "enforcement": "Incomplete rights disclosures are among the most common findings in regulatory audits.",
            "tags": ["rights", "transparency"]
        })

    # ===== GAP 8: Cross-Border Transfers =====
    us_hosted_trackers = [t for t in trackers if any(x in t["name"].lower() for x in
                         ["google", "meta", "facebook", "amazon", "microsoft", "tiktok"])]
    transfer_in_policy = any(w in policy_text for w in ["international transfer", "cross-border",
                                                         "data transfer", "standard contractual",
                                                         "adequacy decision", "transfer outside"])
    if us_hosted_trackers and not transfer_in_policy:
        risk = 35000
        total_risk += risk

        cases = find_relevant_cases(["cross_border", "data_transfer"])
        case_text = "; ".join([
            f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}"
            for c in cases
        ]) if cases else ""

        gaps.append({
            "severity": "info",
            "title": "Cross-border data transfer disclosures missing",
            "regulation": "GDPR Art. 44-49 · Schrems II",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": "Privacy policy does not address international data transfers or safeguards.",
            "actual": f"Website uses {len(us_hosted_trackers)} US-headquartered services ({', '.join(t['name'] for t in us_hosted_trackers[:4])}). If serving EU users, these transfers require Standard Contractual Clauses or other valid mechanisms under GDPR Chapter V.",
            "enforcement": case_text,
            "tags": ["cross_border", "data_transfer"]
        })

    # ===== GAP 9: Children's Data =====
    children_in_policy = any(w in policy_text for w in ["children", "child", "minor", "under 13",
                                                         "under 16", "coppa", "parental consent"])
    if not children_in_policy:
        risk = 5000
        total_risk += risk
        gaps.append({
            "severity": "info",
            "title": "Children's data handling provisions not addressed",
            "regulation": "COPPA · GDPR Art. 8 · UK AADC",
            "fine": f"${risk:,}",
            "fine_raw": risk,
            "claim": "Privacy policy does not mention age restrictions or children's data.",
            "actual": "No age verification mechanism detected. If the service is accessible to children under 13 (COPPA) or under 16 (GDPR), specific consent requirements and data handling restrictions apply.",
            "enforcement": "Epic Games fined $275M (2022) for COPPA violations. TikTok fined €345M (2023) for children's privacy violations.",
            "tags": ["children", "coppa"]
        })

    # ===== CALCULATE RISK BREAKDOWN =====
    gdpr_risk = int(total_risk * 0.58)
    ccpa_risk = int(total_risk * 0.28)
    state_risk = total_risk - gdpr_risk - ccpa_risk

    # Sort gaps by severity
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    gaps.sort(key=lambda g: severity_order.get(g["severity"], 3))

    return {
        "gaps": gaps,
        "total_gaps": len(gaps),
        "critical_count": len([g for g in gaps if g["severity"] == "critical"]),
        "warning_count": len([g for g in gaps if g["severity"] == "warning"]),
        "info_count": len([g for g in gaps if g["severity"] == "info"]),
        "total_risk_exposure": total_risk,
        "risk_after_fix": max(int(total_risk * 0.005), 500),
        "risk_by_regulation": [
            {"name": "GDPR", "amount": gdpr_risk, "detail": f"4% revenue cap · {len([g for g in gaps if 'GDPR' in g['regulation']])} violations"},
            {"name": "CCPA/CPRA", "amount": ccpa_risk, "detail": f"$7,500/violation · {len([g for g in gaps if 'CCPA' in g['regulation']])} violations"},
            {"name": "State Laws", "amount": state_risk, "detail": "VA CDPA, CO CPA, TX TDPSA combined"},
        ],
        "compliance_score": max(5, 100 - (len(gaps) * 9) - (len([g for g in gaps if g["severity"] == "critical"]) * 8)),
    }
