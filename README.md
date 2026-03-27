# Law Firm AI

A private, self-hosted AI platform for law firms — matter-organized document management, RAG-powered chat, a searchable law library with federal court opinion import, and an AI research assistant with automatic web search, confidence scoring, and auto-retry.

---

## Features

### 💬 AI Chat
- Ask questions about any active matter and its uploaded documents
- Retrieval-Augmented Generation (RAG) — answers grounded in firm documents
- Falls back to Claude's legal knowledge when no documents are found
- Powered by the **Meta-Cognitive Reasoning Framework v2.0** for structured, reliable answers

### 📁 Document Management
- Upload PDFs, Word docs, and text files to any matter
- Automatic text extraction, chunking, and vector embedding
- Background processing with status tracking (Processing → Ready)

### 📊 Analytics
- Matter activity, query volume, document counts
- Per-user usage stats and audit log

### ⚙️ Admin
- User management (create, edit, deactivate)
- Role-based access: Admin and Staff
- Full audit trail of all actions

### 📚 Law Library
- Firm-wide repository of legal reference material: case files, statutes, regulations, templates, court records
- Semantic search across all library documents
- **CourtListener integration** — search and import federal/state court opinions directly
- Metadata: jurisdiction, category, citation, court, case date
- All staff can upload; admin-only delete

### 🔍 AI Research Assistant
- Ask any legal research question
- **Three-source parallel pipeline:**
  1. **SearXNG** — self-hosted private web search aggregating Google, Bing, Brave, Presearch, DuckDuckGo
  2. **HuggingFace / Claude** — deep legal knowledge (Qwen2.5-72B or Claude fallback)
  3. **Internal documents** — matter files + law library via ChromaDB
- **Confidence scoring** (0–1) with automatic retry until threshold met (default 0.85)
- Each retry expands all three sources for richer context
- Displays key findings, information gaps, and full source attribution

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy, SQLite |
| Frontend | Streamlit (multi-page) |
| Vector Store | ChromaDB (dual collections) |
| Retrieval | LlamaIndex |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| LLM | Claude claude-sonnet-4-6 (Anthropic) |
| External Knowledge | HuggingFace Inference API (Qwen2.5-72B-Instruct) |
| Web Search | SearXNG (self-hosted, private) |
| Court Opinions | CourtListener API v4 (free, no key required) |
| Auth | JWT (python-jose) |
| Containerization | Docker Compose |

---

## Quick Start

### Prerequisites
- Docker and Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)
- (Optional) A [HuggingFace token](https://huggingface.co/settings/tokens) for Qwen2.5-72B

### 1. Clone and configure

```bash
git clone https://github.com/qwsbtd/Law-Firm-AI.git
cd Law-Firm-AI
cp .env.example .env
```

Edit `.env` and fill in:

```env
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
ADMIN_EMAIL=admin@lawfirm.com
ADMIN_PASSWORD=ChangeMe123!

# Optional but recommended for richer research
HF_TOKEN=hf_...
HF_RESEARCH_MODEL=Qwen/Qwen2.5-72B-Instruct
```

### 2. Build and run

```bash
docker compose up -d --build
```

Three services start:
- **backend** — FastAPI on port 8000
- **frontend** — Streamlit on port 8501
- **searxng** — Private search engine (internal only)

### 3. Open the app

```
http://localhost:8501
```

Log in with your admin credentials from `.env`. Change the password immediately after first login.

---

## Project Structure

```
Law-Firm-AI/
├── backend/
│   ├── api/              # FastAPI routers (auth, chat, documents, matters, library, research, analytics)
│   ├── core/             # Config, database, security
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic (RAG, ChromaDB, library, research, notifications)
│   └── main.py
├── frontend/
│   ├── app.py            # Login page
│   └── pages/
│       ├── 1_💬_Chat.py
│       ├── 2_📁_Documents.py
│       ├── 3_📊_Analytics.py
│       ├── 4_⚙️_Admin.py
│       ├── 5_📚_Library.py
│       └── 6_🔍_Research.py
├── searxng/
│   └── settings.yml      # SearXNG config (engines, JSON API, no rate limiter)
├── nginx/
│   └── law-firm-ai.conf  # Reverse proxy config for production
├── scripts/
│   ├── deploy.sh         # DigitalOcean deployment script
│   └── backup.sh         # Data backup script
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `JWT_SECRET_KEY` | Yes | Random hex string for JWT signing |
| `JWT_EXPIRE_HOURS` | No | Session duration (default: 8) |
| `ADMIN_EMAIL` | Yes | Seeded admin account email |
| `ADMIN_PASSWORD` | Yes | Seeded admin account password |
| `HF_TOKEN` | No | HuggingFace token for Qwen2.5-72B |
| `HF_RESEARCH_MODEL` | No | HF model ID (default: Qwen/Qwen2.5-72B-Instruct) |
| `SEARXNG_URL` | No | SearXNG base URL (default: http://searxng:8080) |
| `SLACK_WEBHOOK_URL` | No | Slack notifications webhook |
| `SMTP_HOST` | No | Email notifications SMTP host |

---

## Data Persistence

All data is stored in a named Docker volume (`law-firm-data`) mounted at `/app/data`:

- `/app/data/law_firm.db` — SQLite database
- `/app/data/chroma/` — ChromaDB vector embeddings
- `/app/data/uploads/` — Uploaded matter documents
- `/app/data/library/` — Law library documents

Back up the volume regularly using `scripts/backup.sh`.

---

## Production Deployment

See `scripts/deploy.sh` for a DigitalOcean deployment script and `nginx/law-firm-ai.conf` for an nginx reverse proxy configuration with SSL termination.

---

## Security Notes

- All API endpoints require JWT authentication
- `.env` is gitignored — never commit credentials
- SearXNG is on the internal Docker network only (no host port exposed)
- Role-based access control: Staff can read/upload; Admins can delete and manage users
- Full audit log of every action stored in SQLite

---

## License

Private — for internal law firm use only.
