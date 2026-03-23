from pathlib import Path

import pandas as pd


def parse_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f'CSV not found: {path}')
    return pd.read_csv(path)
