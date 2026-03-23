import argparse
import asyncio
from pathlib import Path

from embeddings import generate_incident_embeddings
from parsers import parse_csv
from upsert import upsert_incidents, upsert_reservations, upsert_routes, upsert_trips


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='OmniRoute ingest service')
    parser.add_argument('--ops-csv', type=Path, default=Path('ops.csv'))
    parser.add_argument('--reservations-csv', type=Path, default=Path('reservations.csv'))
    parser.add_argument('--incidents-csv', type=Path, default=Path('incidents.csv'))
    parser.add_argument('--with-embeddings', action='store_true')
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    ops_df = parse_csv(args.ops_csv)
    reservations_df = parse_csv(args.reservations_csv)
    incidents_df = parse_csv(args.incidents_csv)

    await upsert_routes(ops_df.to_dict(orient='records'))
    await upsert_trips(ops_df.to_dict(orient='records'))
    await upsert_reservations(reservations_df.to_dict(orient='records'))

    incident_rows = incidents_df.to_dict(orient='records')
    if args.with_embeddings:
        # TODO: Pull provider/model from env and persist vectors to incidents.embedding.
        await generate_incident_embeddings(incident_rows, provider='TODO', model='TODO')

    await upsert_incidents(incident_rows)


if __name__ == '__main__':
    asyncio.run(main())
