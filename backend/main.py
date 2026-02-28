"""
ShieldAI — Main API Server
"""

import os
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
    chat_with_agent,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n🛡️  ShieldAI Server Starting...")
    print("=" * 50)
    oa = os.getenv("OPENAI_API_KEY", "") not in ("", "your_key_here")
    a0 = os.getenv("AUTH0_DOMAIN", "")
    if oa: print("✅ OpenAI API key detected")
    else: print("⚠️  No OpenAI API key")
    if a0: print(f"✅ Auth0: {a0}")
    print(f"\n🌐 Open http://localhost:8000")
    print("=" * 50 + "\n")
    yield


app = FastAPI(title="ShieldAI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

class ScanRequest(BaseModel):
    url: Optional[str] = None
    policy_text: Optional[str] = None

class RewriteRequest(BaseModel):
    gaps: list
    crawl_data: dict

class ChatRequest(BaseModel):
    message: str
    scan_context: dict


@app.get("/")
async def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found"}


@app.get("/api/auth-config")
async def auth_config():
    return {
        "domain": os.getenv("AUTH0_DOMAIN", ""),
        "clientId": os.getenv("AUTH0_CLIENT_ID", ""),
    }


@app.post("/api/scan")
async def run_scan(req: ScanRequest):
    if not req.url and not req.policy_text:
        raise HTTPException(400, "Provide a URL or policy text")

    url = req.url or ""
    if url and not url.startswith("http"):
        url = "https://" + url

    if url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.netloc or "." not in parsed.netloc:
            raise HTTPException(400, "Invalid URL. Enter a real website like https://spotify.com")
        domain = parsed.netloc.replace("www.", "")
        if len(domain) < 4 or len(domain.split(".")[0]) < 2:
            raise HTTPException(400, "Invalid URL. Enter a real website like https://spotify.com")

    crawl_data = None
    if url:
        crawl_result = await crawl_website(url)
        crawl_data = crawl_result.to_dict()
        if crawl_result.errors and not crawl_result.trackers_found and not crawl_result.cookies_detected and not crawl_result.privacy_policy_text:
            raise HTTPException(422, f"Could not reach {url}. Error: {crawl_result.errors[0]}")

    if not crawl_data:
        crawl_data = {
            "url": url, "domain": "", "company_name": "Unknown",
            "trackers_found": [], "cookies_detected": [],
            "forms_detected": [], "consent_banner": {},
            "privacy_policy_text": req.policy_text or "",
            "data_collection_signals": [], "third_party_scripts": [],
            "errors": []
        }

    if req.policy_text:
        crawl_data["privacy_policy_text"] = req.policy_text

    gap_report = analyze_gaps(crawl_data)
    policy_text = crawl_data.get("privacy_policy_text", "")
    policy_clauses = await analyze_policy_with_ai(policy_text or "No policy text available.", crawl_data)
    roadmap = generate_roadmap(gap_report["gaps"])

    return {
        "company": crawl_data.get("company_name", "Unknown"),
        "url": crawl_data.get("url", url),
        "domain": crawl_data.get("domain", ""),
        "trackers_found": crawl_data.get("trackers_found", []),
        "cookies_detected": crawl_data.get("cookies_detected", []),
        "forms_detected": crawl_data.get("forms_detected", []),
        "consent_banner": crawl_data.get("consent_banner", {}),
        "third_party_scripts": crawl_data.get("third_party_scripts", []),
        "data_collection_signals": crawl_data.get("data_collection_signals", []),
        "privacy_policy_found": bool(crawl_data.get("privacy_policy_text")),
        "privacy_policy_url": crawl_data.get("privacy_policy_url", ""),
        "overall_score": gap_report["compliance_score"],
        "total_gaps": gap_report["total_gaps"],
        "critical_gaps": gap_report["critical_count"],
        "total_risk_exposure": gap_report["total_risk_exposure"],
        "risk_after_fix": gap_report["risk_after_fix"],
        "gaps": gap_report["gaps"],
        "risk_by_regulation": gap_report["risk_by_regulation"],
        "policy_clauses": policy_clauses,
        "roadmap": roadmap,
        "errors": crawl_data.get("errors", []),
        "note": gap_report.get("note", ""),
    }


@app.post("/api/rewrite")
async def rewrite_policy(req: RewriteRequest):
    rewritten = await rewrite_policy_clauses(req.gaps, req.crawl_data)
    return {"clauses": rewritten}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    response = await chat_with_agent(req.message, req.scan_context)
    return {"response": response}


@app.get("/api/health")
async def health():
    return {"status": "healthy", "ai": bool(os.getenv("OPENAI_API_KEY", ""))}


@app.get("/{path:path}")
async def catch_all(path: str):
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)