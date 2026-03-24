from collections.abc import Iterable


async def generate_incident_embeddings(rows: Iterable[dict], provider: str, model: str) -> list[list[float]]:
    _ = (rows, provider, model)
    # TODO: Implement async embedding generation pipeline for incidents only.
    return []
