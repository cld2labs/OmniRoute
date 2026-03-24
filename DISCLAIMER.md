# Disclaimer

OmniRoute is provided "as is" and "as available" for internal evaluation,
development, simulation, and demonstration purposes.

OmniRoute is an internal transportation operations simulation and intelligence
platform. It is intended to help internal operators simulate
network activity, inspect operational state, and ask grounded questions about
routes, trips, reservations, utilization, delays, and incidents.

This repository is not represented as production-ready. In particular:

- the platform assumes a trusted internal environment
- the platform does not include authentication, login, JWT, or API key controls
- outputs from the AI query layer must be reviewed by humans before being used
  for operational or business decisions
- vector retrieval is limited to incident narratives and does not replace SQL
  as the source of truth

OmniRoute does not provide legal, compliance, safety, dispatch, or other
professional advice. It does not make autonomous operational decisions, and it
must not be relied on as the sole basis for live transportation actions.

The maintainers are not responsible for any loss, downtime, data issue,
security incident, compliance failure, or operational harm arising from the
use, misuse, deployment, or modification of this repository.
