# Database

- SQLite: `ai_grader.db` (gitignored)
- Migrations: auto-create on startup
- Snapshot JSON is authoritative for PRO diagnostics
- ORM may lag — always prefer snapshot on results reload
