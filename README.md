# Sana’a AI — Home Maintenance Assistant (Backend Service)

Sana’a AI is a modular, RAG-grounded maintenance chatbot service built with **FastAPI** and **Google Gemini Flash**. It provides safe, bilingual (Egyptian Arabic, Modern Standard Arabic, and English) preliminary troubleshooting and technician escalation for home appliances and skilled trades.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.11, 3.12, or 3.13 installed.
- Free Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/).

### 2. Environment Setup

```powershell
# Create virtual environment (if not already created)
py -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure API Key

Copy `.env.example` to `.env` and enter your Gemini API key:

```ini
GEMINI_API_KEY="your-actual-api-key-here"
```

### 4. Run the Development Server

```powershell
uvicorn app.main:app --reload --port 8000
```

Open your browser at:
- **Interactive API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Docs (ReDoc):** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧪 Running Automated Tests

```powershell
pytest
```

---

## 📡 API Endpoints (for Sana'a Mobile & Web Frontend)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Check service health and API key status |
| `POST` | `/api/v1/chat` | Send a user query and receive structured maintenance advice |
| `GET` | `/api/v1/chat/history/{session_id}` | Retrieve history turns for an active session |
| `POST` | `/api/v1/chat/reset` | Clear conversation history for a session |
