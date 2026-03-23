# Security Policy

OmniRoute is an internal platform and does not include production-grade security
controls by default.

## Current Security Posture

The repository currently assumes a trusted internal environment and includes no
authentication or login flow. That means it is not suitable for
public or production deployment without substantial hardening.

## Reported Risks and Expectations

If you discover a security issue, do not open a public issue with exploit
details. Report it privately to the project maintainers through the channel
used for this repository's internal development process.

Before using OmniRoute outside a local or tightly controlled internal
environment, implement and validate at minimum:

- authentication and authorization controls
- secret management and secure configuration
- transport security and encryption at rest where required
- tenant and environment isolation where applicable
- audit logging, monitoring, and alerting
- secure backup, recovery, and incident response procedures
- dependency, container, and image scanning

## Project-Specific Notes

- PostgreSQL is the system of record for structured operational data
- pgvector is limited to incident narrative retrieval and similarity
- the frontend must not access the database directly
- AI outputs must remain grounded in retrieved evidence and require human review

Security fixes, dependency updates, and hardening improvements are welcome, but
the current repository should still be treated as non-production until a full
security review is completed.
