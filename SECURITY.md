# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in everyones-video, please do **not** open a public issue.

Instead, email the maintainer directly at the GitHub profile email listed on the repository.

You should receive a response within 48 hours. If the issue is confirmed, we will release a patch as soon as possible and credit you in the release notes (unless you prefer to remain anonymous).

## Supported Versions

| Version | Supported |
|---------|-----------|
| 6.x     | ✅ |
| 5.x     | ✅ |
| 4.x     | ✅ |
| 3.x     | ❌ |
| 2.x     | ❌ |
| 1.x     | ❌ |

## Security Design

This project follows a defense-in-depth approach:

- **Supply chain**: SHA256 verification for downloaded binaries (render.py)
- **API server**: Token auth, rate limiting (100/min translate, 20/min batch), body size limit (100KB), input validation (language code whitelist, text length caps), CORS restriction, security headers (nosniff, DENY, no-store)
- **Extension**: Manifest V3 CSP, `textContent` only (no innerHTML), only communicates with localhost
- **Container**: Non-root user, .dockerignore, minimal base image
- **Secrets**: API keys read from environment variables only, never logged, never committed

## Dependencies

We pin dependency versions in `requirements.txt` and `Dockerfile`. Run `pip install --require-hashes` or use Docker for reproducible builds.
