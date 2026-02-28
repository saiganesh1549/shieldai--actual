"""
ShieldAI — Tracker & Regulation Knowledge Base
================================================
This file is our "database" of known trackers and real enforcement cases.

TRACKER_SIGNATURES:
  A dictionary of known third-party tracker domains and what they do.
  When the crawler finds one of these domains in a website's HTML/scripts,
  it can immediately identify the tracker by name, category, and what data it collects.
  
  Format: "domain_signature": {"name": "Human Name", "cat": "category", "data": [...]}
  
  Categories:
    - advertising: Ad networks that track users for targeted ads
    - analytics: Tools that measure user behavior  
    - tag_management: Tools that load other scripts (like GTM)
    - customer_data: CRM/chat tools that store user info
    - social: Social media embeds

ENFORCEMENT_CASES:
  Real enforcement actions taken by regulators against companies.
  Used to show users "this is what happened to Company X for the same violation."
  Every case is real — company, fine amount, year, and authority are factual.

find_relevant_cases():
  Given a list of violation tags (e.g., ["advertising", "consent"]),
  finds the most relevant enforcement cases to cite.
"""

# ============================================================
# KNOWN THIRD-PARTY TRACKERS
# Each entry maps a domain substring → tracker info
# When crawler finds this domain in HTML/scripts, it flags it
# ============================================================

TRACKER_SIGNATURES = {
    # --- Advertising Trackers ---
    # These collect user data for targeted advertising
    "google-analytics.com": {"name": "Google Analytics", "cat": "analytics", "data": ["page views", "user behavior", "device info", "IP address"]},
    "googletagmanager.com": {"name": "Google Tag Manager", "cat": "tag_management", "data": ["page views", "events", "user interactions"]},
    "googlesyndication.com": {"name": "Google Ads", "cat": "advertising", "data": ["browsing behavior", "device ID", "ad interactions"]},
    "googleadservices.com": {"name": "Google Ads Conversion", "cat": "advertising", "data": ["conversion events", "device info"]},
    "doubleclick.net": {"name": "DoubleClick (Google)", "cat": "advertising", "data": ["browsing history", "ad impressions", "device fingerprint"]},
    "facebook.net": {"name": "Meta Pixel", "cat": "advertising", "data": ["page views", "custom events", "device info", "hashed emails"]},
    "connect.facebook.net": {"name": "Facebook SDK", "cat": "advertising", "data": ["user interactions", "device info", "browsing behavior"]},
    "facebook.com/tr": {"name": "Meta Tracking Pixel", "cat": "advertising", "data": ["page views", "conversion events"]},
    "tiktok.com": {"name": "TikTok Pixel", "cat": "advertising", "data": ["page views", "events", "device fingerprint"]},
    "analytics.tiktok.com": {"name": "TikTok Analytics", "cat": "advertising", "data": ["page views", "events", "device fingerprint"]},
    "snap.licdn.com": {"name": "LinkedIn Insight Tag", "cat": "advertising", "data": ["page views", "professional profile data"]},
    "ads.linkedin.com": {"name": "LinkedIn Ads", "cat": "advertising", "data": ["conversion events", "professional data"]},
    "bat.bing.com": {"name": "Microsoft Ads UET", "cat": "advertising", "data": ["search behavior", "conversion events"]},
    "criteo.com": {"name": "Criteo", "cat": "advertising", "data": ["browsing behavior", "product views", "device ID"]},
    "criteo.net": {"name": "Criteo Network", "cat": "advertising", "data": ["browsing behavior", "retargeting data"]},
    "amazon-adsystem.com": {"name": "Amazon Ads", "cat": "advertising", "data": ["browsing behavior", "purchase intent"]},
    "pinterest.com/ct": {"name": "Pinterest Tag", "cat": "advertising", "data": ["page views", "conversion events"]},
    "ads.twitter.com": {"name": "X/Twitter Ads", "cat": "advertising", "data": ["page views", "conversion events"]},
    "t.co": {"name": "X/Twitter Click Tracking", "cat": "advertising", "data": ["click tracking", "referral data"]},
    "adsrvr.org": {"name": "The Trade Desk", "cat": "advertising", "data": ["browsing behavior", "device ID", "ad impressions"]},
    "taboola.com": {"name": "Taboola", "cat": "advertising", "data": ["content interactions", "browsing behavior"]},
    "outbrain.com": {"name": "Outbrain", "cat": "advertising", "data": ["content interactions", "browsing behavior"]},
    "adroll.com": {"name": "AdRoll", "cat": "advertising", "data": ["browsing behavior", "retargeting data"]},
    "liveramp.com": {"name": "LiveRamp", "cat": "advertising", "data": ["identity resolution", "cross-device tracking"]},
    "doubleverify.com": {"name": "DoubleVerify", "cat": "advertising", "data": ["ad viewability", "brand safety metrics"]},
    "demdex.net": {"name": "Adobe Audience Manager", "cat": "advertising", "data": ["audience segments", "device IDs"]},

    # --- Analytics Tools ---
    # These measure how users interact with the site
    "hotjar.com": {"name": "Hotjar", "cat": "analytics", "data": ["mouse movements", "clicks", "scrolling", "session recordings"]},
    "clarity.ms": {"name": "Microsoft Clarity", "cat": "analytics", "data": ["session recordings", "heatmaps", "click patterns"]},
    "mixpanel.com": {"name": "Mixpanel", "cat": "analytics", "data": ["user events", "funnels", "user properties"]},
    "segment.io": {"name": "Segment", "cat": "analytics", "data": ["all event data", "user profiles", "cross-platform tracking"]},
    "segment.com": {"name": "Segment", "cat": "analytics", "data": ["all event data", "user profiles", "cross-platform tracking"]},
    "amplitude.com": {"name": "Amplitude", "cat": "analytics", "data": ["user events", "behavioral analytics", "user properties"]},
    "heap.io": {"name": "Heap Analytics", "cat": "analytics", "data": ["auto-captured events", "user sessions"]},
    "fullstory.com": {"name": "FullStory", "cat": "analytics", "data": ["session replay", "clicks", "mouse movement", "form inputs"]},
    "newrelic.com": {"name": "New Relic", "cat": "analytics", "data": ["performance data", "error tracking", "user sessions"]},
    "sentry.io": {"name": "Sentry", "cat": "analytics", "data": ["error reports", "stack traces", "user context"]},
    "plausible.io": {"name": "Plausible", "cat": "analytics", "data": ["page views (privacy-friendly, no cookies)"]},

    # --- Customer Data Platforms ---
    # These collect user identity and interaction data for CRM/support
    "intercom.io": {"name": "Intercom", "cat": "customer_data", "data": ["user identity", "chat messages", "behavioral data"]},
    "zendesk.com": {"name": "Zendesk", "cat": "customer_data", "data": ["support tickets", "user identity"]},
    "hubspot.com": {"name": "HubSpot", "cat": "customer_data", "data": ["form submissions", "email tracking", "CRM data"]},
    "hs-analytics.net": {"name": "HubSpot Analytics", "cat": "customer_data", "data": ["page views", "form interactions", "email opens"]},
    "salesforce.com": {"name": "Salesforce", "cat": "customer_data", "data": ["CRM data", "user interactions"]},
    "drift.com": {"name": "Drift", "cat": "customer_data", "data": ["chat messages", "user identity", "browsing behavior"]},

    # --- Social Media Embeds ---
    "platform.twitter.com": {"name": "Twitter Embed", "cat": "social", "data": ["page views", "user preferences"]},
    "platform.instagram.com": {"name": "Instagram Embed", "cat": "social", "data": ["page views"]},
    "apis.google.com": {"name": "Google APIs", "cat": "social", "data": ["authentication data"]},
}

# ============================================================
# REAL ENFORCEMENT CASES
# Every case here is a real fine issued by a real regulator.
# We cite these when we find similar violations on scanned sites.
# ============================================================

ENFORCEMENT_CASES = [
    {
        "company": "Meta/Facebook", "fine": "€1.2B", "fine_usd": 1300000000,
        "year": 2023, "authority": "Irish DPC",
        "violation": "EU-to-US data transfers without adequate safeguards",
        "tags": ["cross_border", "data_transfer"]
    },
    {
        "company": "Meta/Facebook", "fine": "€390M", "fine_usd": 425000000,
        "year": 2023, "authority": "Irish DPC",
        "violation": "Lack of valid legal basis for behavioral advertising",
        "tags": ["advertising", "consent", "legal_basis"]
    },
    {
        "company": "Google", "fine": "€150M", "fine_usd": 163000000,
        "year": 2022, "authority": "CNIL (France)",
        "violation": "Making cookie rejection harder than acceptance",
        "tags": ["cookies", "consent"]
    },
    {
        "company": "Facebook", "fine": "€60M", "fine_usd": 65000000,
        "year": 2022, "authority": "CNIL (France)",
        "violation": "Cookie consent mechanism not providing equal reject option",
        "tags": ["cookies", "consent"]
    },
    {
        "company": "Amazon Europe", "fine": "€746M", "fine_usd": 812000000,
        "year": 2021, "authority": "Luxembourg CNPD",
        "violation": "Processing personal data for advertising without proper consent",
        "tags": ["advertising", "consent"]
    },
    {
        "company": "Epic Games/Fortnite", "fine": "$275M", "fine_usd": 275000000,
        "year": 2022, "authority": "FTC",
        "violation": "COPPA violations — collecting children's data without parental consent",
        "tags": ["children", "coppa", "consent"]
    },
    {
        "company": "Sephora", "fine": "$1.2M", "fine_usd": 1200000,
        "year": 2022, "authority": "California AG",
        "violation": "Undisclosed sale of consumer data via third-party trackers",
        "tags": ["advertising", "disclosure", "ccpa"]
    },
    {
        "company": "BetterHelp", "fine": "$7.8M", "fine_usd": 7800000,
        "year": 2023, "authority": "FTC",
        "violation": "Sharing health data with advertising platforms without disclosure",
        "tags": ["advertising", "disclosure", "health_data"]
    },
    {
        "company": "Google", "fine": "$391.5M", "fine_usd": 391500000,
        "year": 2022, "authority": "40 US States",
        "violation": "Misleading location tracking practices",
        "tags": ["location", "disclosure", "deceptive"]
    },
    {
        "company": "Clearview AI", "fine": "€20M", "fine_usd": 22000000,
        "year": 2022, "authority": "Italian DPA",
        "violation": "Unlawful processing of biometric/facial recognition data",
        "tags": ["biometric", "consent", "disclosure"]
    },
    {
        "company": "TikTok", "fine": "€345M", "fine_usd": 345000000,
        "year": 2023, "authority": "Irish DPC",
        "violation": "Children's privacy violations and transparency failures",
        "tags": ["children", "transparency", "consent"]
    },
    {
        "company": "Deutsche Wohnen", "fine": "€14.5M", "fine_usd": 14500000,
        "year": 2019, "authority": "Berlin DPA",
        "violation": "Failing to establish proper data retention and deletion practices",
        "tags": ["retention", "deletion"]
    },
    {
        "company": "Deliveroo", "fine": "€2.5M", "fine_usd": 2500000,
        "year": 2021, "authority": "Italian DPA",
        "violation": "Collecting excessive data beyond service necessity",
        "tags": ["minimization", "excessive_collection"]
    },
    {
        "company": "Amazon/Alexa", "fine": "$25M", "fine_usd": 25000000,
        "year": 2023, "authority": "FTC",
        "violation": "Retaining children's voice data and geolocation indefinitely",
        "tags": ["children", "retention", "location"]
    },
    {
        "company": "H&M", "fine": "€35.3M", "fine_usd": 38000000,
        "year": 2020, "authority": "Hamburg DPA",
        "violation": "Extensive surveillance of employees including health and private data",
        "tags": ["employee_data", "excessive_collection"]
    },
    {
        "company": "WhatsApp", "fine": "€225M", "fine_usd": 245000000,
        "year": 2021, "authority": "Irish DPC",
        "violation": "Insufficient transparency about data sharing with Meta companies",
        "tags": ["transparency", "disclosure", "sharing"]
    },
]


def find_relevant_cases(tags: list[str], limit: int = 2) -> list[dict]:
    """
    Find enforcement cases that match the given violation tags.
    
    How it works:
    1. For each case, count how many of our search tags match the case's tags
    2. Sort by most matches first, then by largest fine
    3. Return the top N cases
    
    Example: find_relevant_cases(["advertising", "consent"]) 
    → Returns Meta €390M case and Amazon €746M case (both match advertising + consent)
    """
    scored = []
    for case in ENFORCEMENT_CASES:
        # Count overlapping tags between what we're looking for and this case
        overlap = len(set(tags) & set(case["tags"]))
        if overlap > 0:
            scored.append((overlap, case))

    # Sort: most tag matches first, then largest fine first
    scored.sort(key=lambda x: (-x[0], -x[1]["fine_usd"]))

    # Return just the case dicts (not the scores)
    return [c for _, c in scored[:limit]] 