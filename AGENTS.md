This is MediKiosk, a solo-built AI clinical history-taking prototype for Smart India Hackathon problem statement SIH26047.

Tech stack:
- Backend: Python FastAPI, running on port 8080 (not 8000, due to a Windows port permission issue)
- Frontend: React with Vite
- LLM: Ollama running llama3.1:8b locally at http://localhost:11434
- Speech-to-text: faster-whisper
- Text-to-speech: Piper TTS
- Database: SQLite
- OCR: PaddleOCR

Rules:
- All clinical data must match the structure in docs/schema.json
- Keep code simple and readable - this is a hackathon prototype, not production software
- Before starting any task, check ROADMAP.md for current progress and what's next
- After completing a task, update ROADMAP.md to mark it done, then commit the changes to git
