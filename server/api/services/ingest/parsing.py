from __future__ import annotations

import csv
import io
import json


class CSVParsingError(ValueError):
    pass


class MissingColumnsError(ValueError):
    def __init__(self, missing_columns: list[str]):
        self.missing_columns = missing_columns
        joined = ', '.join(missing_columns)
        super().__init__(f'Missing required CSV columns: {joined}')


def _decode_csv(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise CSVParsingError('CSV must be UTF-8 encoded.') from exc


def read_csv_columns(file_bytes: bytes) -> list[str]:
    text = _decode_csv(file_bytes)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CSVParsingError('CSV header row is required.')
    return [column.strip() for column in reader.fieldnames]


def read_csv_bytes(file_bytes: bytes) -> list[dict[str, str]]:
    text = _decode_csv(file_bytes)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CSVParsingError('CSV header row is required.')

    rows: list[dict[str, str]] = []
    for row in reader:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in row.items():
            key = (raw_key or '').strip()
            value = '' if raw_value is None else str(raw_value).strip()
            normalized[key] = value
        rows.append(normalized)
    return rows


def parse_stops_json(stops_json_str: str) -> list[dict]:
    raw = stops_json_str.strip()
    if not raw:
        raise CSVParsingError('stops_json is required.')

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CSVParsingError('stops_json must be valid JSON.') from exc

    if not isinstance(parsed, list):
        raise CSVParsingError('stops_json must be a JSON array.')

    for item in parsed:
        if not isinstance(item, dict):
            raise CSVParsingError('stops_json must be an array of objects.')
    return parsed
