# Security and usage scope

**This is a learning/portfolio project, not a production ITSM application.**

- There is **no authentication, authorization, tenant isolation, rate limiting or CSRF protection**. Every caller with network access can read or modify incidents and notes.
- Run on **127.0.0.1 only**, or publish the container port to `127.0.0.1:8000`. Do not expose it publicly or connect it to real customer systems.
- Use **synthetic records only**. Never store customer PII, API keys, passwords, support tickets, sensitive infrastructure details, or real production incident evidence.
- SQLite stores incident records on disk. The `.gitignore` excludes SQLite database files; backups, mounts and exports still need operator care.
- SQL operations are parameterized. The browser renders user-controlled data via `textContent` and avoids HTML injection.
- CSV exports prefix values that could become formulas in spreadsheet viewers. Treat exported files as private if you add private information.
- The local demo uses no cloud credentials, telemetry ingestion, third-party APIs, email or secrets.
- The Docker image starts as a non-root user, but the application is still intentionally unauthenticated.
- Real production use would require identity and role-based access, proper audit integrity, request throttling, HTTPS, backups, retention controls, migrations, security testing, and observability.
