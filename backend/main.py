"""
ShieldAI — Main API Server

This is the entry point for the entire backend. It:
1. Serves the frontend HTML page to the browser
2. Exposes REST API endpoints for scanning, rewriting, and chatting
3. Orchestrates the full scan pipeline: crawl → gap analysis → AI audit → roadmap

Tech stack: FastAPI (Python web framework), Uvicorn (ASGI server)
"""

import os
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

# FastAPI — modern Python web framework for building APIs
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
# Pydantic — validates incoming request data automatically
from pydantic import BaseModel
from typing import Optional
# python-dotenv — loads API keys from .env file so they aren't hardcoded
from dotenv import load_dotenv

# Our custom modules — each handles a different part of the pipeline
from crawler import crawl_website          # Step 1: Visit the website and extract data
from gap_analyzer import analyze_gaps      # Step 2: Compare detected behavior vs policy claims
from ai_rewriter import (
    analyze_policy_with_ai,                # Step 3: AI grades each section of the policy
    rewrite_policy_clauses,                # Step 4: AI writes compliant replacement clauses
    generate_roadmap,                      # Step 5: Prioritized fix-it plan
    chat_with_agent,                       # Bonus: Interactive AI privacy advisor
)

# Load environment variables from .env file (API keys, Auth0 config)
load_dotenv()


# ============================================================
# SERVER STARTUP — runs once when the server boots
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup — checks which services are configured and prints status."""
    print("\n🛡️  ShieldAI Server Starting...")
    print("=" * 50)

    # Check if OpenAI API key is present in .env
    oa = os.getenv("OPENAI_API_KEY", "") not in ("", "your_key_here")
    # Check if Auth0 is configured for login
    a0 = os.getenv("AUTH0_DOMAIN", "")

    if oa: print("✅ OpenAI API key detected")
    else: print("⚠️  No OpenAI API key — AI features will be unavailable")
    if a0: print(f"✅ Auth0: {a0}")

    print(f"\n🌐 Open http://localhost:8000")
    print("=" * 50 + "\n")
    yield  # Server runs here until shutdown


# ============================================================
# APP INITIALIZATION
# ============================================================

# Create the FastAPI application instance
app = FastAPI(title="ShieldAI", version="1.0.0", lifespan=lifespan)

# CORS middleware — allows the frontend (running on same origin) to talk to the API
# In production you'd restrict this, but for hackathon demo we allow all origins
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Path to the frontend directory (one level up from backend/)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ============================================================
# REQUEST MODELS — define what data each endpoint expects
# Pydantic validates these automatically and returns 422 if wrong
# ============================================================

class ScanRequest(BaseModel):
    """POST /api/scan — user provides a URL and optionally pasted policy text."""
    url: Optional[str] = None
    policy_text: Optional[str] = None  # Manual policy paste (when crawler can't find it)

class RewriteRequest(BaseModel):
    """POST /api/rewrite — takes detected gaps and crawl data, returns fixed clauses."""
    gaps: list         # The compliance gaps found by gap_analyzer
    crawl_data: dict   # Raw crawl results (trackers, cookies, etc.)

class ChatRequest(BaseModel):
    """POST /api/chat — user's message + scan context for the AI advisor."""
    message: str       # What the user asked
    scan_context: dict # Current scan results so AI can reference them


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
async def serve_frontend():
    """Serve the main HTML page when user visits http://localhost:8000."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found"}


@app.get("/api/auth-config")
async def auth_config():
    """Return Auth0 configuration to the frontend so it can initialize login.
    The frontend calls this on page load to set up the Auth0 SDK."""
    return {
        "domain": os.getenv("AUTH0_DOMAIN", ""),
        "clientId": os.getenv("AUTH0_CLIENT_ID", ""),
    }


@app.post("/api/scan")
async def run_scan(req: ScanRequest):
    """
    MAIN SCAN ENDPOINT — the core of ShieldAI.

    Full pipeline:
    1. Validate the URL (reject garbage input like "asdf")
    2. Crawl the website (detect trackers, cookies, forms, consent banner, privacy policy)
    3. Analyze gaps (compare what's detected vs what the policy claims)
    4. AI audit (GPT grades each section of the privacy policy)
    5. Generate remediation roadmap (prioritized fix plan with time estimates)
    6. Return everything to the frontend
    """

    # Must provide either a URL to scan or policy text to analyze
    if not req.url and not req.policy_text:
        raise HTTPException(400, "Provide a URL or policy text")

    url = req.url or ""
    # Auto-prepend https:// if user just typed "spotify.com"
    if url and not url.startswith("http"):
        url = "https://" + url

    # ===== INPUT VALIDATION =====
    # Reject obviously invalid URLs (no TLD, too short, etc.)
    if url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.netloc or "." not in parsed.netloc:
            raise HTTPException(400, "Invalid URL. Enter a real website like https://spotify.com")
        domain = parsed.netloc.replace("www.", "")
        if len(domain) < 4 or len(domain.split(".")[0]) < 2:
            raise HTTPException(400, "Invalid URL. Enter a real website like https://spotify.com")

    # ===== STEP 1: CRAWL THE WEBSITE =====
    crawl_data = None
    if url:
        crawl_result = await crawl_website(url)  # This does all the heavy lifting
        crawl_data = crawl_result.to_dict()

        # If crawl completely failed (no data at all), tell the user
        if crawl_result.errors and not crawl_result.trackers_found and not crawl_result.cookies_detected and not crawl_result.privacy_policy_text:
            raise HTTPException(422, f"Could not reach {url}. Error: {crawl_result.errors[0]}")

    # If no crawl data (e.g., user only pasted policy text), create empty structure
    if not crawl_data:
        crawl_data = {
            "url": url, "domain": "", "company_name": "Unknown",
            "trackers_found": [], "cookies_detected": [],
            "forms_detected": [], "consent_banner": {},
            "privacy_policy_text": req.policy_text or "",
            "data_collection_signals": [], "third_party_scripts": [],
            "errors": []
        }

    # If user pasted policy text manually, use that instead of (or in addition to) crawled text
    if req.policy_text:
        crawl_data["privacy_policy_text"] = req.policy_text

    # ===== STEP 2: GAP ANALYSIS =====
    # Compares detected trackers/cookies/forms against what the policy says
    gap_report = analyze_gaps(crawl_data)

    # ===== STEP 3: AI POLICY AUDIT =====
    # Sends policy text + detected evidence to GPT, gets back graded sections
    policy_text = crawl_data.get("privacy_policy_text", "")
    policy_clauses = await analyze_policy_with_ai(policy_text or "No policy text available.", crawl_data)

    # ===== STEP 4: REMEDIATION ROADMAP =====
    # Turns gaps into a prioritized action plan with time/cost estimates
    roadmap = generate_roadmap(gap_report["gaps"])

    # ===== RETURN EVERYTHING TO FRONTEND =====
    return {
        # Company info
        "company": crawl_data.get("company_name", "Unknown"),
        "url": crawl_data.get("url", url),
        "domain": crawl_data.get("domain", ""),

        # Raw crawl findings (displayed in agent panel)
        "trackers_found": crawl_data.get("trackers_found", []),
        "cookies_detected": crawl_data.get("cookies_detected", []),
        "forms_detected": crawl_data.get("forms_detected", []),
        "consent_banner": crawl_data.get("consent_banner", {}),
        "third_party_scripts": crawl_data.get("third_party_scripts", []),
        "data_collection_signals": crawl_data.get("data_collection_signals", []),
        "privacy_policy_found": bool(crawl_data.get("privacy_policy_text")),
        "privacy_policy_url": crawl_data.get("privacy_policy_url", ""),

        # Gap analysis results (displayed in main dashboard)
        "overall_score": gap_report["compliance_score"],
        "total_gaps": gap_report["total_gaps"],
        "critical_gaps": gap_report["critical_count"],
        "total_risk_exposure": gap_report["total_risk_exposure"],
        "risk_after_fix": gap_report["risk_after_fix"],
        "gaps": gap_report["gaps"],
        "risk_by_regulation": gap_report["risk_by_regulation"],

        # AI-generated audit (Policy Audit tab)
        "policy_clauses": policy_clauses,

        # Remediation plan (Remediation tab)
        "roadmap": roadmap,

        # Any errors or notes from the analysis
        "errors": crawl_data.get("errors", []),
        "note": gap_report.get("note", ""),
    }


@app.post("/api/rewrite")
async def rewrite_policy(req: RewriteRequest):
    """AI generates compliant replacement clauses for each detected gap.
    Called when user clicks 'Rewrite Policy' button."""
    rewritten = await rewrite_policy_clauses(req.gaps, req.crawl_data)
    return {"clauses": rewritten}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Interactive AI privacy advisor — answers user questions about their scan results.
    The AI sees the current scan context so it can reference specific findings."""
    response = await chat_with_agent(req.message, req.scan_context)
    return {"response": response}


@app.get("/api/health")
async def health():
    """Simple health check — used to verify the server is running."""
    return {"status": "healthy", "ai": bool(os.getenv("OPENAI_API_KEY", ""))}


# ============================================================
# STATIC FILE SERVING — catch-all for any frontend assets
# ============================================================

@app.get("/{path:path}")
async def catch_all(path: str):
    """Serves any static files (CSS, JS, images) from the frontend directory.
    Falls back to index.html for client-side routing."""
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")


# ============================================================
# ENTRY POINT — run with: python main.py
# ============================================================

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000 with auto-reload (restarts when code changes)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)