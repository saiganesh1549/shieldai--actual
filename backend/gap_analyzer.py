"""
ShieldAI — Gap Analyzer
Detects gaps between what a privacy policy claims and what
the website/product actually does.

CORE RULE: Only flag a gap if we have EVIDENCE on BOTH sides.
- We detected something (tracker, cookie, form field, signal)
- AND the policy either doesn't mention it or contradicts it
- If we couldn't find the policy, we say so — we do NOT assume violations.
"""

from knowledge_base import find_relevant_cases


def analyze_gaps(crawl_data: dict, policy_analysis: dict | None = None) -> dict:
    gaps = []
    total_risk = 0

    trackers = crawl_data.get("trackers_found", [])
    forms = crawl_data.get("forms_detected", [])
    signals = crawl_data.get("data_collection_signals", [])
    consent = crawl_data.get("consent_banner", {})
    policy_text = crawl_data.get("privacy_policy_text", "").lower()
    has_policy = len(policy_text) > 200  # Did we actually get real policy text?

    # ===== GAP 1: Undisclosed Advertising Trackers =====
    # Only flag if we DETECTED trackers — this is always evidence-based
    ad_trackers = [t for t in trackers if t.get("category") == "advertising"]
    if ad_trackers:
        tracker_names = [t["name"] for t in ad_trackers]
        all_data = list(set(d for t in ad_trackers for d in t.get("data_shared", [])))

        # If we have the policy, check if trackers are disclosed
        if has_policy:
            undisclosed = []
            for t in ad_trackers:
                name_lower = t["name"].lower().split()[0]
                if name_lower not in policy_text and t.get("signature", "").lower() not in policy_text:
                    undisclosed.append(t["name"])
            claim_text = f"Privacy policy {'mentions general \"partners\" but does not name: ' + ', '.join(undisclosed) if undisclosed else 'discloses some ad partners'}."
        else:
            undisclosed = tracker_names  # Can't verify disclosure without policy
            claim_text = "Could not retrieve privacy policy to verify tracker disclosure."

        risk = len(ad_trackers) * 68000
        total_risk += risk
        cases = find_relevant_cases(["advertising", "disclosure", "consent"])
        case_text = "; ".join([f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}" for c in cases]) if cases else "Multiple companies fined for undisclosed tracking."

        gaps.append({
            "severity": "critical" if undisclosed else "warning",
            "title": f"{len(ad_trackers)} advertising trackers detected" + (f" — {len(undisclosed)} not disclosed in policy" if has_policy and undisclosed else ""),
            "regulation": "CCPA §1798.140(e) · CCPA §1798.115 · GDPR Art. 13(1)(e)",
            "fine": f"${risk:,}", "fine_raw": risk,
            "claim": claim_text,
            "actual": f"Detected on the page: {', '.join(tracker_names)}. These collect: {', '.join(all_data[:6])}.",
            "enforcement": case_text,
            "tags": ["advertising", "disclosure"]
        })

    # Non-ad trackers worth noting
    analytics_trackers = [t for t in trackers if t.get("category") == "analytics"]
    if analytics_trackers and has_policy:
        undisclosed_analytics = [t["name"] for t in analytics_trackers if t["name"].lower().split()[0] not in policy_text]
        if undisclosed_analytics:
            risk = len(undisclosed_analytics) * 15000
            total_risk += risk
            gaps.append({
                "severity": "warning",
                "title": f"{len(undisclosed_analytics)} analytics tools detected but not named in policy",
                "regulation": "GDPR Art. 13(1)(e) · CCPA §1798.100(b)",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": "Privacy policy does not specifically name these analytics providers.",
                "actual": f"Detected analytics tools: {', '.join(undisclosed_analytics)}. GDPR requires disclosure of specific data recipients.",
                "enforcement": "Transparency about analytics providers is a standard requirement under GDPR Art. 13.",
                "tags": ["analytics", "disclosure"]
            })

    # ===== GAP 2: Cookie Consent Issues =====
    # Only flag if consent banner analysis found real issues
    consent_issues = consent.get("issues", [])
    if consent_issues:
        risk = 180000
        total_risk += risk
        cases = find_relevant_cases(["cookies", "consent"])
        case_text = "; ".join([f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}" for c in cases]) if cases else ""

        gaps.append({
            "severity": "critical",
            "title": "Cookie consent issues detected",
            "regulation": "GDPR Art. 7 · ePrivacy Directive Art. 5(3) · CCPA §1798.120",
            "fine": f"${risk:,}", "fine_raw": risk,
            "claim": f"{'Cookie consent banner detected' if consent.get('detected') else 'No cookie consent banner found on the page'}" + (f" (provider: {consent.get('provider')})" if consent.get('provider') else "") + ".",
            "actual": ". ".join(consent_issues) + ". GDPR requires freely given, specific, informed consent with equal prominence for accept and reject.",
            "enforcement": case_text,
            "tags": ["cookies", "consent"]
        })

    # ===== GAP 3: Location Data =====
    # Only flag if we DETECTED geolocation code
    location_signals = [s for s in signals if s["category"] == "geolocation"]
    if location_signals:
        location_in_policy = has_policy and any(w in policy_text for w in ["location", "geolocation", "gps", "geographic"])
        if not location_in_policy:
            risk = 2100000
            total_risk += risk
            cases = find_relevant_cases(["location", "disclosure"])
            case_text = "; ".join([f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}" for c in cases]) if cases else ""
            gaps.append({
                "severity": "critical",
                "title": "Location tracking code detected" + (" — not disclosed in policy" if has_policy else ""),
                "regulation": "GDPR Art. 13(1)(e) · CCPA §1798.100(b)",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": "Privacy policy does not mention location data collection." if has_policy else "Could not retrieve privacy policy to verify location disclosure.",
                "actual": f"Detected: {', '.join(s['description'] for s in location_signals)}. Location data is classified as sensitive personal information.",
                "enforcement": case_text,
                "tags": ["location", "disclosure"]
            })

    # ===== GAP 4: Session Recording =====
    # Only flag if we DETECTED recording tools
    recording_signals = [s for s in signals if s["category"] == "session_recording"]
    if recording_signals:
        recording_in_policy = has_policy and any(w in policy_text for w in ["session recording", "session replay", "screen recording", "hotjar", "fullstory", "clarity"])
        if not recording_in_policy:
            risk = 95000
            total_risk += risk
            gaps.append({
                "severity": "warning",
                "title": "Session recording tools detected" + (" — not disclosed in policy" if has_policy else ""),
                "regulation": "GDPR Art. 13 · CCPA §1798.100(b) · ePrivacy Art. 5(3)",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": "Privacy policy does not disclose session recording." if has_policy else "Could not verify disclosure — privacy policy not retrieved.",
                "actual": f"Detected: {', '.join(s['description'] for s in recording_signals)}. Session recording captures mouse movements, clicks, scrolling, and form input.",
                "enforcement": "Session recording without disclosure flagged by multiple EU DPAs as transparency violation.",
                "tags": ["recording", "transparency"]
            })

    # ===== THE FOLLOWING GAPS ONLY APPLY IF WE HAVE THE ACTUAL POLICY TEXT =====
    # If we couldn't find the policy, we DO NOT flag these — that would be guessing.

    if has_policy:
        # ===== GAP 5: Data Retention =====
        retention_keywords = ["retention period", "retain your data for", "store your data for",
                             "delete after", "retained for", "keep your data for", "days", "months", "years"]
        has_specific_retention = any(kw in policy_text for kw in retention_keywords)
        vague_retention = any(w in policy_text for w in ["as long as necessary", "as needed", "reasonable period"])

        if not has_specific_retention or (vague_retention and not has_specific_retention):
            risk = 45000
            total_risk += risk
            cases = find_relevant_cases(["retention", "deletion"])
            case_text = "; ".join([f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}" for c in cases]) if cases else ""
            gaps.append({
                "severity": "warning",
                "title": "Data retention periods " + ("vague" if vague_retention else "not specified"),
                "regulation": "GDPR Art. 13(2)(a) · CCPA §1798.100(a)(3)",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": f"Privacy policy {'uses vague language like \"as long as necessary\" without specific periods' if vague_retention else 'does not specify data retention periods'}.",
                "actual": "GDPR requires specific storage periods or clear criteria. Vague language has been consistently found non-compliant by EU DPAs.",
                "enforcement": case_text,
                "tags": ["retention", "transparency"]
            })

        # ===== GAP 6: Missing Rights Disclosure =====
        rights_keywords = {
            "access": ["right to access", "right of access", "access your data", "request a copy", "access request"],
            "deletion": ["right to deletion", "right to erasure", "delete your data", "right to be forgotten", "request deletion"],
            "portability": ["data portability", "portable format", "machine-readable", "export your data"],
            "objection": ["right to object", "object to processing", "opt out of processing"],
            "opt_out_sale": ["do not sell", "opt-out of sale", "opt out of the sale", "do not share"],
        }
        missing_rights = [right for right, keywords in rights_keywords.items() if not any(kw in policy_text for kw in keywords)]

        if len(missing_rights) >= 2:  # Only flag if multiple rights missing — one could be wording difference
            risk = 8000 * len(missing_rights)
            total_risk += risk
            gaps.append({
                "severity": "warning" if len(missing_rights) >= 3 else "info",
                "title": f"User rights disclosure incomplete — missing {len(missing_rights)} rights",
                "regulation": "GDPR Art. 15-22 · CCPA §1798.100-125",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": "Privacy policy mentions some user rights but does not cover all required rights.",
                "actual": f"Could not find disclosure of: {', '.join(r.replace('_', ' ').title() for r in missing_rights)}. Both GDPR and CCPA require clear disclosure of all applicable rights.",
                "enforcement": "Incomplete rights disclosures are among the most common findings in regulatory audits.",
                "tags": ["rights", "transparency"]
            })

        # ===== GAP 7: Cross-Border Transfers =====
        # Only flag if we detected US-based services AND policy doesn't mention transfers
        us_trackers = [t for t in trackers if any(x in t["name"].lower() for x in ["google", "meta", "facebook", "amazon", "microsoft", "tiktok"])]
        transfer_in_policy = any(w in policy_text for w in ["international transfer", "cross-border", "data transfer", "standard contractual", "adequacy decision", "transfer outside", "transferred to", "united states"])

        if us_trackers and not transfer_in_policy:
            risk = 35000
            total_risk += risk
            cases = find_relevant_cases(["cross_border", "data_transfer"])
            case_text = "; ".join([f"{c['company']} fined {c['fine']} by {c['authority']} ({c['year']}) for {c['violation']}" for c in cases]) if cases else ""
            gaps.append({
                "severity": "info",
                "title": "Cross-border data transfers not addressed in policy",
                "regulation": "GDPR Art. 44-49",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": "Privacy policy does not address international data transfers.",
                "actual": f"Detected {len(us_trackers)} US-based services ({', '.join(t['name'] for t in us_trackers[:4])}). For EU users, transfers require SCCs or other valid mechanisms.",
                "enforcement": case_text,
                "tags": ["cross_border", "data_transfer"]
            })

        # ===== GAP 8: Children's Data =====
        # Only flag if policy has zero mention — this is a real compliance gap
        children_in_policy = any(w in policy_text for w in ["children", "child", "minor", "under 13", "under 16", "coppa", "parental consent", "age"])
        if not children_in_policy:
            risk = 5000
            total_risk += risk
            gaps.append({
                "severity": "info",
                "title": "Children's data provisions not addressed in policy",
                "regulation": "COPPA · GDPR Art. 8 · UK AADC",
                "fine": f"${risk:,}", "fine_raw": risk,
                "claim": "Privacy policy does not mention age restrictions or children's data handling.",
                "actual": "No age verification mechanism detected and no children's data section in privacy policy. If accessible to minors, COPPA and GDPR Art. 8 requirements apply.",
                "enforcement": "Epic Games fined $275M (2022) for COPPA violations. TikTok fined €345M (2023) for children's privacy failures.",
                "tags": ["children", "coppa"]
            })

    # ===== GAP 6 (alternative): Excessive Data in Forms =====
    excessive_fields = []
    for form in forms:
        for f in form.get("fields", []):
            name_lower = f["name"].lower()
            if any(x in name_lower for x in ["phone", "tel", "mobile", "birth", "dob", "age", "address", "street", "zip", "postal", "ssn", "social security", "gender", "sex"]):
                if f.get("required", False):
                    excessive_fields.append(f["name"])

    if excessive_fields:
        risk = 12000 * len(excessive_fields)
        total_risk += risk
        gaps.append({
            "severity": "warning",
            "title": f"Forms require {len(excessive_fields)} potentially excessive fields",
            "regulation": "GDPR Art. 5(1)(c) — Data Minimization",
            "fine": f"${risk:,}", "fine_raw": risk,
            "claim": "Data minimization requires only collecting necessary data." if "minim" in policy_text else "Policy does not address data minimization.",
            "actual": f"Detected required fields: {', '.join(excessive_fields[:5])}. These may not be necessary for core service functionality.",
            "enforcement": "Deliveroo fined €2.5M (2021) for collecting excessive data beyond service necessity.",
            "tags": ["minimization", "excessive_collection"]
        })

    # If we found NOTHING — no trackers, no consent issues, no policy — be honest
    if not gaps and not has_policy:
        return {
            "gaps": [],
            "total_gaps": 0, "critical_count": 0, "warning_count": 0, "info_count": 0,
            "total_risk_exposure": 0, "risk_after_fix": 0,
            "compliance_score": 0,  # 0 = "unable to determine", not "perfect"
            "risk_by_regulation": [
                {"name": "GDPR", "amount": 0, "detail": "Could not retrieve policy for analysis"},
                {"name": "CCPA/CPRA", "amount": 0, "detail": "Could not retrieve policy for analysis"},
                {"name": "State Laws", "amount": 0, "detail": "Could not retrieve policy for analysis"},
            ],
            "note": "Unable to retrieve privacy policy. Use Advanced Options to paste policy text for a complete analysis."
        }

    # Calculate risk breakdown
    gdpr_risk = int(total_risk * 0.58)
    ccpa_risk = int(total_risk * 0.28)
    state_risk = total_risk - gdpr_risk - ccpa_risk

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    gaps.sort(key=lambda g: severity_order.get(g["severity"], 3))

    critical_count = len([g for g in gaps if g["severity"] == "critical"])
    gap_count = len(gaps)

    return {
        "gaps": gaps,
        "total_gaps": gap_count,
        "critical_count": critical_count,
        "warning_count": len([g for g in gaps if g["severity"] == "warning"]),
        "info_count": len([g for g in gaps if g["severity"] == "info"]),
        "total_risk_exposure": total_risk,
        "risk_after_fix": max(int(total_risk * 0.005), 500) if total_risk > 0 else 0,
        "risk_by_regulation": [
            {"name": "GDPR", "amount": gdpr_risk, "detail": f"{len([g for g in gaps if 'GDPR' in g['regulation']])} violations found"},
            {"name": "CCPA/CPRA", "amount": ccpa_risk, "detail": f"{len([g for g in gaps if 'CCPA' in g['regulation']])} violations found"},
            {"name": "State Laws", "amount": state_risk, "detail": "VA CDPA, CO CPA, TX TDPSA combined"},
        ],
        "compliance_score": max(5, 100 - (gap_count * 9) - (critical_count * 8)) if gap_count > 0 else (85 if has_policy else 0),
    } 