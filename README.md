# Student Manager System — Group 02

Repository: ```bash `https://github.com/nguyendzz/StudentManagerSystem_Group02.git`

## Architecture
- Pattern: **MVC (Model – View – Controller)** (Chapter 3)
- Database: SQLite 3NF relational schema (13 tables)
- Language & GUI: Python (Flask Web GUI)
- Testing: `pytest`
- Deployment: Docker

## Quick Start (Local)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest -v
python run.py
```

Default Admin account: `admin` / `Admin123`

## Quick Start (Docker)
```bash
docker build -t sms-group02 .
docker run -p 5000:5000 sms-group02
```
