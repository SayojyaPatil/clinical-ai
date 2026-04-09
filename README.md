# Clinical AI — Note Summarizer

A FastAPI backend that extracts structured clinical data from doctor notes using AI. Supports both typed text and handwritten image uploads.

## What it does

Send a doctor's note and get back structured JSON with diagnoses, medications with dose and frequency, follow-up actions, urgency level (routine / urgent / emergent), and a confidence score with warning flag.

## Tech Stack

Python, FastAPI, PydanticAI, GPT-4o Vision, SQLAlchemy, SQLite, JWT, Pydantic v2

## Setup

Clone the repo and create a virtual environment:
```bash
git clone https://github.com/SayojyaPatil/clinical-ai.git
cd clinical-ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:
OPENAI_API_KEY=your-openai-key
SECRET_KEY=your-secret-key

Run the server:
```bash
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive API documentation.


## Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/auth/signup` | Create account |
| POST | `/auth/token` | Login |
| POST | `/notes/analyze-text` | Analyze typed note |
| POST | `/notes/analyze-image` | Analyze handwritten image |
| GET | `/notes` | List notes |
| GET | `/notes/{id}` | Get note by ID |


## Real World Use Case

Doctors spend 2 hours on paperwork for every 1 hour with patients. This API automates clinical documentation by extracting structured data from free-text notes for use in hospital EHR systems, billing, and pharmacy orders.

## Project Structure
```
app/
├── main.py        — app factory
├── models.py      — pydantic models
├── database.py    — database setup
├── agent.py       — AI logic
├── security.py    — JWT auth
└── routers/
    ├── auth.py    — signup and login endpoints
    └── notes.py   — note endpoints
```


## Author

Sayojya Patil