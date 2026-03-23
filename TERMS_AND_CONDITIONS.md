# Terms and Conditions

These Terms and Conditions govern access to and use of **OmniRoute**.

By accessing, using, copying, modifying, or distributing this repository, you
agree to the following:

- OmniRoute is an internal transportation operations simulation and
  intelligence platform
- the repository is provided on an "as is" and "as available" basis
- you are responsible for deployment, configuration, security, compliance, and
  operational use
- you must independently validate outputs before using them in real-world
  operational workflows
- you must not represent the current platform as a production-ready managed service
  or safety-critical decision system

## Use Restrictions

You agree not to:

- use the system as a substitute for human operational judgment
- rely on AI-generated responses that are not grounded in retrieved evidence
- expand vector search to structured route, trip, or reservation data in a way
  that conflicts with project constraints
- expose the platform publicly without adding appropriate security controls
- use real secrets or unauthorized sensitive data in shared or insecure
  environments

## Project Constraints

OmniRoute is designed around the following operating assumptions:

- PostgreSQL is the source of truth for exact facts and aggregations
- pgvector is used only for incident narratives, explanations, and similarity
- the current platform has no authentication, login, JWT, or API key flow
- all services are expected to run through the repository's Docker-based stack

## Liability

To the maximum extent permitted by law, the maintainers and contributors are
not liable for any claim, loss, damage, operational disruption, data issue, or
compliance failure arising from use of this repository.
