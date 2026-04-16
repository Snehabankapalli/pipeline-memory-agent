# Contributing

Thanks for your interest in pipeline-memory-agent.

## Setup

```bash
git clone https://github.com/Snehabankapalli/pipeline-memory-agent.git
cd pipeline-memory-agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running Tests

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

Coverage target: 80%+.

## Running the Dashboard

```bash
uvicorn src.dashboard.app:app --reload --port 8000
```

Visit `http://localhost:8000`.

## Development Workflow

1. Fork the repo + create a feature branch: `git checkout -b feat/your-feature`
2. Write tests first (TDD). Implementation should make tests pass
3. Format: `black src/ tests/` + lint: `ruff check src/ tests/`
4. Commit with conventional message: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
5. Push + open a PR against `main`

## Code Standards

- Functions <50 lines; modules <400 lines
- Docstrings on every public function
- No hardcoded secrets — use environment variables
- All errors handled with context (never silent `except: pass`)

## Pull Request Checklist

- [ ] Tests pass with 80%+ coverage
- [ ] No hardcoded secrets or credentials
- [ ] README updated if behavior changed
- [ ] Added to CHANGELOG if user-facing

## Reporting Bugs

Open an issue with: repro steps, expected vs actual behavior, Python version, and relevant logs.
