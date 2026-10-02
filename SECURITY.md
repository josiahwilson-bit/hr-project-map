# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| < 0.4   | :x:                |

## Reporting a vulnerability

**Do not file public issues for security vulnerabilities.**

Report them privately by email to the maintainer. Include:
- A description of the vulnerability
- Steps to reproduce
- The version affected
- Any suggested fix (optional)

You will receive an acknowledgment, and the issue will be addressed in a
timely manner. If the vulnerability is confirmed, a fix will be released
and credited (with your permission).

## Scope notes

hr-project-map is a local-first tool: it runs on your machine, stores data
in local SQLite/JSON files, has no network functionality, no
authentication system, and no third-party runtime dependencies (Python
standard library only). Its attack surface is correspondingly small, but
reports are still welcome — especially around the CLI's handling of
untrusted input files.
