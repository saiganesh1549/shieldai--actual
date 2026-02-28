"""
ShieldAI — Website Crawler
Scans a website and detects trackers, cookies, data collection forms,
consent banners, and third-party scripts.

Key improvement: also fetches common subpages (privacy policy, terms)
and checks script src URLs for tracker domains, not just inline HTML.
"""

import re
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
import httpx

from knowledge_base import TRACKER_SIGNATURES


@dataclass
class CrawlResult:
    url: str = ""
    domain: str = ""
    company_name: str = ""
    page_title: str = ""
    trackers_found: list = field(default_factory=list)
    cookies_detected: list = field(default_factory=list)
    forms_detected: list = field(default_factory=list)
    consent_banner: dict = field(default_factory=dict)
    privacy_policy_url: str = ""
    privacy_policy_text: str = ""
    third_party_scripts: list = field(default_factory=list)
    data_collection_signals: list = field(default_factory=list)
    meta_tags: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def to_dict(self):
        return {
            "url": self.url,
            "domain": self.domain,
            "company_name": self.company_name,
            "page_title": self.page_title,
            "trackers_found": self.trackers_found,
            "cookies_detected": self.cookies_detected,
            "forms_detected": self.forms_detected,
            "consent_banner": self.consent_banner,
            "privacy_policy_url": self.privacy_policy_url,
            "privacy_policy_text": self.privacy_policy_text,
            "third_party_scripts": self.third_party_scripts,
            "data_collection_signals": self.data_collection_signals,
            "errors": self.errors,
        }


# Common privacy policy paths to try when we can't find a link
COMMON_POLICY_PATHS = [
    "/privacy",
    "/privacy-policy",
    "/legal/privacy-policy",
    "/legal/privacy",
    "/privacy/policy",
    "/about/privacy",
    "/policies/privacy",
    "/en/privacy",
    "/legal",
    "/terms/privacy",
]


async def crawl_website(url: str) -> CrawlResult:
    """Crawl a website and extract privacy-relevant information."""
    result = CrawlResult(url=url)

    if not url.startswith("http"):
        url = "https://" + url
    result.url = url

    parsed = urlparse(url)
    result.domain = parsed.netloc.replace("www.", "")
    result.company_name = result.domain.split(".")[0].capitalize()

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        ) as client:
            resp = await client.get(url)
            html = resp.text

            # Collect ALL cookies from response headers too
            for cookie_name, cookie_value in resp.cookies.items():
                result.cookies_detected.append({
                    "name": cookie_name,
                    "value": cookie_value[:50] + "..." if len(cookie_value) > 50 else cookie_value,
                    "type": classify_cookie(cookie_name)
                })

            # Also check Set-Cookie headers directly (catches more)
            for header_val in resp.headers.get_list("set-cookie"):
                cookie_name = header_val.split("=")[0].strip()
                if cookie_name and not any(c["name"] == cookie_name for c in result.cookies_detected):
                    result.cookies_detected.append({
                        "name": cookie_name,
                        "value": "(from header)",
                        "type": classify_cookie(cookie_name)
                    })

            soup = BeautifulSoup(html, "html.parser")

            title_tag = soup.find("title")
            result.page_title = title_tag.get_text(strip=True) if title_tag else result.company_name

            # ===== DETECT TRACKERS =====
            # Check both the HTML content AND all script src URLs
            result.trackers_found = detect_trackers(html, soup)

            # ===== DETECT THIRD-PARTY SCRIPTS =====
            result.third_party_scripts = detect_third_party_scripts(soup, result.domain)

            # Cross-reference: any third-party script domain that matches a known tracker
            for script in result.third_party_scripts:
                script_domain = script["domain"].lower()
                for sig, info in TRACKER_SIGNATURES.items():
                    if sig.lower() in script_domain:
                        already = any(t["name"] == info["name"] for t in result.trackers_found)
                        if not already:
                            result.trackers_found.append({
                                "name": info["name"],
                                "category": info["cat"],
                                "data_shared": info["data"],
                                "signature": sig,
                                "source": "script_src"
                            })

            # ===== DETECT FORMS & DATA COLLECTION =====
            result.forms_detected = detect_forms(soup)
            result.data_collection_signals = detect_data_collection(soup, html)

            # ===== DETECT CONSENT BANNER =====
            result.consent_banner = detect_consent_banner(soup, html)

            # ===== FIND PRIVACY POLICY =====
            # Method 1: Look for link in the page HTML
            result.privacy_policy_url = find_privacy_policy_link(soup, url)

            # Method 2: If no link found, brute-force common paths with GET (HEAD fails on many sites)
            if not result.privacy_policy_url:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                extended_paths = COMMON_POLICY_PATHS + [
                    f"/en-us/privacy",
                    f"/en-gb/privacy",
                    f"/us/legal/privacy",
                    f"/help/privacy",
                    f"/info/privacy",
                    f"/pages/privacy",
                    f"/privacy.html",
                    f"/site/privacy",
                    f"/{result.domain.split('.')[0]}/privacy",  # e.g. /depop/privacy
                ]
                for path in extended_paths:
                    try:
                        test_url = base_url + path
                        pp_test = await client.get(test_url)
                        if pp_test.status_code < 400:
                            # Verify it's actually a privacy page, not a redirect to homepage
                            test_text = pp_test.text.lower()
                            if any(kw in test_text for kw in ["privacy policy", "privacy notice", "personal data", "personal information", "data protection", "we collect"]):
                                result.privacy_policy_url = test_url
                                break
                    except:
                        continue

            # ===== FETCH & PARSE PRIVACY POLICY =====
            if result.privacy_policy_url:
                try:
                    pp_resp = await client.get(result.privacy_policy_url)
                    if pp_resp.status_code < 400:
                        pp_soup = BeautifulSoup(pp_resp.text, "html.parser")
                        for tag in pp_soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
                            tag.decompose()
                        # Try to get the main content area first
                        main = pp_soup.find("main") or pp_soup.find("article") or pp_soup.find(role="main") or pp_soup.find("div", class_=re.compile("content|body|main|policy|privacy", re.I))
                        if main:
                            text = main.get_text(separator="\n", strip=True)
                        else:
                            text = pp_soup.get_text(separator="\n", strip=True)
                        # Verify this is real policy text
                        if len(text) > 300 and any(kw in text.lower() for kw in ["privacy", "personal data", "we collect", "information"]):
                            result.privacy_policy_text = text[:15000]
                        elif len(text) > 200:
                            result.privacy_policy_text = text[:15000]
                            result.errors.append("Privacy policy page found but text may be incomplete (JS-rendered site)")
                        else:
                            result.errors.append("Privacy policy URL found but page contained very little readable text — likely requires JavaScript to render")
                except Exception as e:
                    result.errors.append(f"Could not fetch privacy policy: {str(e)}")
            else:
                result.errors.append("Could not automatically locate a privacy policy page. Use Advanced Options to paste the policy text manually.")

            # ===== ALSO CRAWL ONE MORE PAGE (e.g. /login or /signup) FOR MORE DATA =====
            try:
                signup_paths = ["/signup", "/register", "/join", "/account/login", "/login"]
                for spath in signup_paths:
                    try:
                        signup_url = f"{parsed.scheme}://{parsed.netloc}{spath}"
                        signup_resp = await client.get(signup_url)
                        if signup_resp.status_code < 400:
                            signup_soup = BeautifulSoup(signup_resp.text, "html.parser")
                            # Check for additional trackers
                            extra_trackers = detect_trackers(signup_resp.text, signup_soup)
                            for et in extra_trackers:
                                if not any(t["name"] == et["name"] for t in result.trackers_found):
                                    et["source"] = "signup_page"
                                    result.trackers_found.append(et)
                            # Check for forms
                            extra_forms = detect_forms(signup_soup)
                            if extra_forms:
                                for ef in extra_forms:
                                    ef["source"] = spath
                                result.forms_detected.extend(extra_forms)
                            # Check for more data collection signals
                            extra_signals = detect_data_collection(signup_soup, signup_resp.text)
                            for es in extra_signals:
                                if not any(s["signal"] == es["signal"] for s in result.data_collection_signals):
                                    result.data_collection_signals.append(es)
                            break  # Only need one successful page
                    except:
                        continue
            except:
                pass

    except httpx.ConnectError:
        result.errors.append(f"Could not connect to {url}. The site may be down or blocking our request.")
    except httpx.TimeoutException:
        result.errors.append(f"Connection to {url} timed out after 20 seconds.")
    except Exception as e:
        result.errors.append(f"Crawl error: {str(e)}")

    return result


def detect_trackers(html: str, soup: BeautifulSoup) -> list:
    """Detect known trackers in page HTML, inline scripts, and script src URLs."""
    found = []
    html_lower = html.lower()

    # Check 1: Look for tracker domains in the full HTML (catches inline references)
    for domain_sig, info in TRACKER_SIGNATURES.items():
        if domain_sig.lower() in html_lower:
            found.append({
                "name": info["name"],
                "category": info["cat"],
                "data_shared": info["data"],
                "signature": domain_sig,
                "source": "html"
            })

    # Check 2: Look inside all <script> tags for tracker function calls
    tracker_functions = {
        "gtag(": {"name": "Google Analytics/Ads", "cat": "analytics", "data": ["page views", "events", "conversions"]},
        "ga('": {"name": "Google Analytics (Legacy)", "cat": "analytics", "data": ["page views", "user behavior"]},
        "ga(\"": {"name": "Google Analytics (Legacy)", "cat": "analytics", "data": ["page views", "user behavior"]},
        "fbq(": {"name": "Meta Pixel", "cat": "advertising", "data": ["page views", "custom events", "conversions"]},
        "ttq.": {"name": "TikTok Pixel", "cat": "advertising", "data": ["page views", "events", "device fingerprint"]},
        "twq(": {"name": "Twitter/X Pixel", "cat": "advertising", "data": ["page views", "conversion events"]},
        "pintrk(": {"name": "Pinterest Tag", "cat": "advertising", "data": ["page views", "conversion events"]},
        "snaptr(": {"name": "Snapchat Pixel", "cat": "advertising", "data": ["page views", "conversion events"]},
        "lintrk(": {"name": "LinkedIn Insight", "cat": "advertising", "data": ["page views", "professional data"]},
        "_hj(": {"name": "Hotjar", "cat": "analytics", "data": ["session recordings", "heatmaps", "clicks"]},
        "hj(": {"name": "Hotjar", "cat": "analytics", "data": ["session recordings", "heatmaps", "clicks"]},
        "clarity(": {"name": "Microsoft Clarity", "cat": "analytics", "data": ["session recordings", "heatmaps"]},
        "mixpanel": {"name": "Mixpanel", "cat": "analytics", "data": ["user events", "funnels", "user properties"]},
        "amplitude": {"name": "Amplitude", "cat": "analytics", "data": ["user events", "behavioral analytics"]},
        "segment.": {"name": "Segment", "cat": "analytics", "data": ["all event data", "user profiles"]},
        "optimizely": {"name": "Optimizely", "cat": "analytics", "data": ["A/B test data", "user segments"]},
        "heap.track": {"name": "Heap Analytics", "cat": "analytics", "data": ["auto-captured events", "sessions"]},
        "intercom(": {"name": "Intercom", "cat": "customer_data", "data": ["user identity", "chat messages"]},
        "Intercom(": {"name": "Intercom", "cat": "customer_data", "data": ["user identity", "chat messages"]},
    }

    for sig, info in tracker_functions.items():
        if sig in html:
            already = any(t["name"] == info["name"] for t in found)
            if not already:
                found.append({
                    "name": info["name"],
                    "category": info["cat"],
                    "data_shared": info["data"],
                    "signature": sig.strip("(.'\""),
                    "source": "inline_script"
                })

    # Check 3: Look at all script src attributes
    for tag in soup.find_all("script", src=True):
        src = (tag.get("src") or "").lower()
        for domain_sig, info in TRACKER_SIGNATURES.items():
            if domain_sig.lower() in src:
                already = any(t["name"] == info["name"] for t in found)
                if not already:
                    found.append({
                        "name": info["name"],
                        "category": info["cat"],
                        "data_shared": info["data"],
                        "signature": domain_sig,
                        "source": "script_src"
                    })

    # Check 4: Look at link/img tags (tracking pixels are often 1x1 images)
    for tag in soup.find_all("img", src=True):
        src = (tag.get("src") or "").lower()
        for domain_sig, info in TRACKER_SIGNATURES.items():
            if domain_sig.lower() in src:
                already = any(t["name"] == info["name"] for t in found)
                if not already:
                    found.append({
                        "name": info["name"],
                        "category": info["cat"],
                        "data_shared": info["data"],
                        "signature": domain_sig,
                        "source": "pixel_img"
                    })

    # Deduplicate by name
    seen = set()
    deduped = []
    for t in found:
        if t["name"] not in seen:
            seen.add(t["name"])
            deduped.append(t)

    return deduped


def detect_third_party_scripts(soup: BeautifulSoup, own_domain: str) -> list:
    """Find all third-party script sources."""
    scripts = []
    for tag in soup.find_all("script", src=True):
        src = tag["src"]
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("http"):
            script_parsed = urlparse(src)
            script_domain = script_parsed.netloc.replace("www.", "")
            if own_domain not in script_domain and script_domain:
                already = any(s["domain"] == script_domain for s in scripts)
                if not already:
                    scripts.append({
                        "domain": script_domain,
                        "src": src[:150]
                    })
    # Also check link tags with rel=preconnect (sites preconnect to tracker domains)
    for tag in soup.find_all("link", rel=True):
        if "preconnect" in tag.get("rel", []) or "dns-prefetch" in tag.get("rel", []):
            href = tag.get("href", "")
            if href.startswith("http"):
                link_parsed = urlparse(href)
                link_domain = link_parsed.netloc.replace("www.", "")
                if own_domain not in link_domain and link_domain:
                    already = any(s["domain"] == link_domain for s in scripts)
                    if not already:
                        scripts.append({
                            "domain": link_domain,
                            "src": href,
                            "type": "preconnect"
                        })
    return scripts


def detect_forms(soup: BeautifulSoup) -> list:
    """Detect data collection forms and what fields they require."""
    forms = []
    for form in soup.find_all("form"):
        fields = []
        for inp in form.find_all(["input", "select", "textarea"]):
            input_type = inp.get("type", "text").lower()
            input_name = inp.get("name", inp.get("id", inp.get("placeholder", "unknown")))
            if input_type in ("hidden", "submit", "button", "csrf", "token"):
                continue
            required = inp.has_attr("required") or inp.get("aria-required") == "true"
            fields.append({
                "name": str(input_name)[:50],
                "type": input_type,
                "required": required
            })
        if fields:
            action = form.get("action", "self")
            forms.append({
                "action": str(action)[:100],
                "method": form.get("method", "GET").upper(),
                "fields": fields
            })
    return forms


def detect_data_collection(soup: BeautifulSoup, html: str) -> list:
    """Detect signals of data collection beyond forms."""
    signals = []
    html_lower = html.lower()

    checks = [
        ("geolocation", "navigator.geolocation", "Geolocation API detected — collecting user location"),
        ("geolocation", "getCurrentPosition", "GPS location tracking code detected"),
        ("device_fingerprint", "fingerprint", "Device fingerprinting code detected"),
        ("device_fingerprint", "canvas.toDataURL", "Canvas fingerprinting technique detected"),
        ("local_storage", "localStorage.setItem", "Storing data in browser localStorage"),
        ("session_recording", "mouseflow", "Session recording tool detected (Mouseflow)"),
        ("session_recording", "hotjar", "Session recording tool detected (Hotjar)"),
        ("session_recording", "fullstory", "Session recording tool detected (FullStory)"),
        ("session_recording", "clarity.ms", "Session recording tool detected (Microsoft Clarity)"),
        ("push_notifications", "PushManager", "Push notification subscription detected"),
        ("camera_microphone", "getUserMedia", "Camera/microphone access code detected"),
        ("clipboard", "clipboard.readText", "Clipboard reading code detected"),
        ("webrtc", "RTCPeerConnection", "WebRTC detected — can expose real IP behind VPN"),
        ("battery", "navigator.getBattery", "Battery status API detected"),
        ("bluetooth", "navigator.bluetooth", "Bluetooth API access detected"),
    ]

    for category, signature, description in checks:
        if signature.lower() in html_lower:
            signals.append({
                "category": category,
                "signal": signature,
                "description": description
            })

    return signals


def detect_consent_banner(soup: BeautifulSoup, html: str) -> dict:
    """Detect and analyze cookie consent banner."""
    html_lower = html.lower()

    banner = {
        "detected": False,
        "has_reject": False,
        "has_granular": False,
        "loads_before_consent": False,
        "provider": None,
        "issues": []
    }

    consent_providers = {
        "onetrust": "OneTrust",
        "cookiebot": "Cookiebot",
        "trustarc": "TrustArc",
        "cookieconsent": "CookieConsent",
        "osano": "Osano",
        "termly": "Termly",
        "iubenda": "Iubenda",
        "quantcast": "Quantcast Choice",
        "didomi": "Didomi",
        "usercentrics": "Usercentrics",
        "consentmanager": "Consent Manager",
        "sp_consent": "Sourcepoint",
    }

    for sig, name in consent_providers.items():
        if sig in html_lower:
            banner["detected"] = True
            banner["provider"] = name
            break

    consent_keywords = ["cookie consent", "cookie banner", "cookie notice", "accept cookies",
                       "cookie policy", "we use cookies", "this site uses cookies",
                       "consent-banner", "cookie-banner", "cookie-consent",
                       "gdpr-consent", "privacy-consent", "cookieNotice"]
    for kw in consent_keywords:
        if kw.lower() in html_lower:
            banner["detected"] = True
            break

    reject_keywords = ["reject all", "decline all", "deny all", "refuse all", 
                       "reject cookies", "decline cookies", "opt out",
                       "reject-all", "decline-all"]
    for kw in reject_keywords:
        if kw.lower() in html_lower:
            banner["has_reject"] = True
            break

    granular_keywords = ["manage preferences", "cookie preferences", "cookie settings",
                        "customize cookies", "manage cookies", "cookie-settings",
                        "manage-preferences", "privacy preferences"]
    for kw in granular_keywords:
        if kw.lower() in html_lower:
            banner["has_granular"] = True
            break

    # Determine issues
    if not banner["detected"]:
        banner["issues"].append("No cookie consent banner detected")
    else:
        if not banner["has_reject"]:
            banner["issues"].append("No 'Reject All' option — GDPR requires equal prominence for rejection")
        if not banner["has_granular"]:
            banner["issues"].append("No granular cookie category controls detected")

    # Check if trackers load before consent
    inline_trackers = ["gtag(", "fbq(", "ttq.", "_gaq.", "ga('create", "ga(\"create",
                       "analytics.js", "gtm.js"]
    for sig in inline_trackers:
        if sig in html:
            banner["loads_before_consent"] = True
            banner["issues"].append("Tracking scripts load before user consent is given")
            break

    return banner


def find_privacy_policy_link(soup: BeautifulSoup, base_url: str) -> str:
    """Find the privacy policy link on the page."""
    pp_patterns = ["privacy policy", "privacy notice", "privacy statement",
                   "data policy", "privacy"]

    # Check all links
    for link in soup.find_all("a", href=True):
        link_text = link.get_text(strip=True).lower()
        href = link["href"].lower()

        for pattern in pp_patterns:
            if pattern in link_text or "privacy" in href:
                full_url = link["href"]
                if full_url.startswith("/"):
                    full_url = urljoin(base_url, full_url)
                elif not full_url.startswith("http"):
                    full_url = urljoin(base_url, full_url)
                return full_url

    return ""


def classify_cookie(name: str) -> str:
    """Classify a cookie as essential, analytics, advertising, or functional."""
    name_lower = name.lower()

    advertising = ["_fbp", "_fbc", "fr", "_gcl", "IDE", "test_cookie", "_uetsid",
                   "_uetvid", "NID", "MUID", "_pin_unauth", "li_sugr", "_tt_",
                   "ads", "_scid", "personalization_id"]
    analytics = ["_ga", "_gid", "_gat", "__utma", "__utmb", "__utmc", "__utmz",
                 "_hjid", "_hjSession", "mp_", "amplitude", "ajs_", "_clck",
                 "_clsk", "ab.", "optimizely"]
    essential = ["csrf", "session", "PHPSESSID", "JSESSIONID", "connect.sid",
                "__stripe", "cart", "checkout", "auth", "token", "sid",
                "logged_in", "secure"]

    for sig in advertising:
        if sig.lower() in name_lower:
            return "advertising"
    for sig in analytics:
        if sig.lower() in name_lower:
            return "analytics"
    for sig in essential:
        if sig.lower() in name_lower:
            return "essential"

    return "unknown"