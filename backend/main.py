"""
ShieldAI — Main API Server
Ties together crawling, gap analysis, AI rewriting, and serves the frontend.
"""

import os
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from crawler import crawl_website
from gap_analyzer import analyze_gaps
from ai_rewriter import (
    analyze_policy_with_ai,
    rewrite_policy_clauses,
    generate_roadmap,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n🛡️  ShieldAI Server Starting...")
    print("=" * 50)

    # Check for API keys
    has_gemini = os.getenv("GEMINI_API_KEY", "your_key_here") != "your_key_here"
    has_openai = os.getenv("OPENAI_API_KEY", "your_key_here") != "your_key_here"
    has_groq = os.getenv("GROQ_API_KEY", "your_key_here") != "your_key_here"

   
    if has_openai:
        print("✅ OpenAI API key detected")
    else:
        print("⚠️  No AI API key found — using template-based analysis")
        print("   Get a free key at https://aistudio.google.com")

    print(f"\n🌐 Open http://localhost:8000 in your browser")
    print("=" * 50 + "\n")
    yield


app = FastAPI(title="ShieldAI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ============================================================
# REQUEST MODELS
# ============================================================

class ScanRequest(BaseModel):
    url: Optional[str] = None
    policy_text: Optional[str] = None
    app_store_url: Optional[str] = None
    play_store_url: Optional[str] = None


class RewriteRequest(BaseModel):
    gaps: list
    crawl_data: dict


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found. Place index.html in frontend/ directory."}


@app.post("/api/scan")
async def run_scan(req: ScanRequest):
    """
    Full compliance scan pipeline:
    1. Validate input
    2. Crawl website
    3. Analyze gaps (ONLY from real detected data)
    4. Analyze policy clauses
    5. Calculate risk
    6. Generate roadmap
    """
    if not req.url and not req.policy_text:
        raise HTTPException(400, "Provide a URL or policy text")

    url = req.url or ""
    if url and not url.startswith("http"):
        url = "https://" + url

    # ===== INPUT VALIDATION =====
    if url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # Must have a real domain with a dot (e.g. example.com)
        if not parsed.netloc or "." not in parsed.netloc:
            raise HTTPException(400, "Invalid URL. Enter a real website like https://spotify.com")
        # Block obvious garbage
        domain = parsed.netloc.replace("www.", "")
        if len(domain) < 4 or len(domain.split(".")[0]) < 2:
            raise HTTPException(400, "Invalid URL. Enter a real website like https://spotify.com")

    # Step 1: Crawl
    crawl_data = None
    if url:
        crawl_result = await crawl_website(url)
        crawl_data = crawl_result.to_dict()

        # If crawl had fatal errors and got NO data, tell the user
        if crawl_result.errors and not crawl_result.trackers_found and not crawl_result.cookies_detected and not crawl_result.privacy_policy_text:
            raise HTTPException(422, f"Could not reach {url}. Check the URL and try again. Error: {crawl_result.errors[0]}")

    if not crawl_data:
        crawl_data = {
            "url": url, "domain": "", "company_name": "Unknown",
            "trackers_found": [], "cookies_detected": [],
            "forms_detected": [], "consent_banner": {},
            "privacy_policy_text": req.policy_text or "",
            "data_collection_signals": [], "third_party_scripts": [],
            "errors": []
        }

    # If user provided policy text, use that
    if req.policy_text:
        crawl_data["privacy_policy_text"] = req.policy_text

    # Step 2: Analyze gaps
    gap_report = analyze_gaps(crawl_data)

    # Step 3: Analyze policy clauses with AI
    policy_text = crawl_data.get("privacy_policy_text", "")
    if policy_text:
        policy_clauses = await analyze_policy_with_ai(policy_text, crawl_data)
    else:
        policy_clauses = await analyze_policy_with_ai("No privacy policy text available.", crawl_data)

    # Step 4: Generate roadmap
    roadmap = generate_roadmap(gap_report["gaps"])

    # Build response
    return {
        "company": crawl_data.get("company_name", "Unknown"),
        "url": crawl_data.get("url", url),
        "domain": crawl_data.get("domain", ""),

        # Crawl data
        "trackers_found": crawl_data.get("trackers_found", []),
        "cookies_detected": crawl_data.get("cookies_detected", []),
        "forms_detected": crawl_data.get("forms_detected", []),
        "consent_banner": crawl_data.get("consent_banner", {}),
        "third_party_scripts": crawl_data.get("third_party_scripts", []),
        "data_collection_signals": crawl_data.get("data_collection_signals", []),
        "privacy_policy_found": bool(crawl_data.get("privacy_policy_text")),
        "privacy_policy_url": crawl_data.get("privacy_policy_url", ""),

        # Gap analysis
        "overall_score": gap_report["compliance_score"],
        "total_gaps": gap_report["total_gaps"],
        "critical_gaps": gap_report["critical_count"],
        "total_risk_exposure": gap_report["total_risk_exposure"],
        "risk_after_fix": gap_report["risk_after_fix"],
        "gaps": gap_report["gaps"],
        "risk_by_regulation": gap_report["risk_by_regulation"],

        # Policy analysis
        "policy_clauses": policy_clauses,

        # Roadmap
        "roadmap": roadmap,

        # Errors
        "errors": crawl_data.get("errors", []),
    }


@app.post("/api/rewrite")
async def rewrite_policy(req: RewriteRequest):
    """Generate AI-rewritten policy clauses that close detected gaps."""
    rewritten = await rewrite_policy_clauses(req.gaps, req.crawl_data)
    return {"clauses": rewritten}


@app.post("/api/rewrite/stream")
async def rewrite_policy_stream(req: RewriteRequest):
    """Stream rewritten clauses as Server-Sent Events."""

    async def event_generator():
        clauses = await rewrite_policy_clauses(req.gaps, req.crawl_data)
        for i, clause in enumerate(clauses):
            # Send each clause as an SSE event
            data = json.dumps(clause)
            yield f"data: {data}\n\n"
            await asyncio.sleep(0.3)  # Small delay between clauses
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    has_ai = any([
        os.getenv("GEMINI_API_KEY", "your_key_here") != "your_key_here",
        os.getenv("OPENAI_API_KEY", "your_key_here") != "your_key_here",
        os.getenv("GROQ_API_KEY", "your_key_here") != "your_key_here",
    ])
    return {
        "status": "healthy",
        "ai_enabled": has_ai,
        "version": "1.0.0"
    }


# ============================================================
# STATIC FILE SERVING (catch-all for frontend assets)
# ============================================================

@app.get("/{path:path}")
async def catch_all(path: str):
    """Serve static frontend files."""
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    # Fall back to index.html for SPA routing
    return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)