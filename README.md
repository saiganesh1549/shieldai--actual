# 🛡️ ShieldAI — Privacy Compliance War Room

**Built at CUhackit '26 | Clemson University**

ShieldAI finds the gaps between what companies *claim* in their privacy policies and what their products *actually do* — then fixes those gaps with AI-powered policy rewriting.

## 🚀 Quick Start (2 minutes)

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Add your AI API key (optional but recommended)
```bash
cp .env.example .env
# Edit .env and add your key:
# GEMINI_API_KEY=your_key    (FREE at https://aistudio.google.com)
# OR OPENAI_API_KEY=your_key
# OR GROQ_API_KEY=your_key   (FREE at https://console.groq.com)
```

**Note:** ShieldAI works WITHOUT an API key using template-based analysis. The AI key enables smarter, contextual policy rewriting.

### 3. Run the server
```bash
cd backend
python main.py
```

### 4. Open in browser
```
http://localhost:8000
```

## 🏗️ Project Structure
```
shieldai/
├── frontend/
│   └── index.html          # Full React-style SPA (single file)
├── backend/
│   ├── main.py             # FastAPI server & API endpoints
│   ├── crawler.py          # Website scanner (trackers, cookies, forms)
│   ├── gap_analyzer.py     # Gap detection engine (claims vs reality)
│   ├── ai_rewriter.py      # AI policy rewriter (Gemini/OpenAI/Groq)
│   ├── knowledge_base.py   # Tracker DB, enforcement cases, regulations
│   ├── requirements.txt    # Python dependencies
│   ├── .env.example        # Environment variable template
│   └── .env                # Your API keys (create this)
└── README.md
```

## 🔧 Tech Stack
- **Frontend:** Vanilla HTML/CSS/JS with custom dashboard UI
- **Backend:** Python FastAPI
- **Web Crawling:** httpx + BeautifulSoup4
- **AI:** Google Gemini 2.0 Flash (free) / OpenAI / Groq
- **Streaming:** Server-Sent Events (SSE) for live rewriting

## 📊 What It Analyzes
1. **Website Crawl** — Detects cookies, trackers, scripts, data collection forms
2. **Policy Parser** — Clause-by-clause analysis against GDPR, CCPA, state laws
3. **Gap Detection** — Cross-references policy claims vs actual detected behavior
4. **Risk Calculator** — Financial exposure based on real enforcement precedents
5. **AI Rewriter** — Generates compliant policy language closing each gap
6. **Compliance Roadmap** — Prioritized fixes ranked by risk reduction

## 📋 Regulations Covered
- GDPR (EU General Data Protection Regulation)
- CCPA/CPRA (California Consumer Privacy Act)
- ePrivacy Directive (Cookie Law)
- COPPA (Children's Online Privacy Protection)
- Virginia CDPA, Colorado CPA, Texas TDPSA
- UK Age Appropriate Design Code (AADC)

## 🏆 Challenge Submissions
- **Capstone Industry Impact Challenge** — Privacy compliance gap between policy claims and product behavior
- **Launchpad Startup Toolkit Challenge** — AI tool helping founders avoid regulatory fines
- **Auto: Most Innovative + Best Execution**

## 👥 Team
- Built by Clemson Privacy Compliance Creative Inquiry researchers
- CUhackit '26 — February 14-16, 2026
