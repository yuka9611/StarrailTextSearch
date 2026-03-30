from __future__ import annotations

from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_ROOT.parent
DATA_ROOT = (PROJECT_ROOT.parent / "turnbasedgamedata").resolve()
TEXTMAP_ROOT = DATA_ROOT / "TextMap"
EXCEL_OUTPUT_ROOT = DATA_ROOT / "ExcelOutput"
STORY_ROOT = DATA_ROOT / "Story"
CONFIG_LEVEL_ROOT = DATA_ROOT / "Config" / "Level"
DB_PATH = SERVER_ROOT / "data.db"
DB_TMP_PATH = SERVER_ROOT / "data.db.tmp"
