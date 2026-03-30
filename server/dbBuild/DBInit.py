from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from dbBuild.builder import StarrailDatabaseBuilder


def build() -> None:
    builder = StarrailDatabaseBuilder()
    builder.initialize_empty_database()
    print("Initialized empty database schema at server/data.db")


if __name__ == "__main__":
    build()
