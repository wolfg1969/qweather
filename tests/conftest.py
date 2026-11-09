"""Make the pure mapping module importable without Home Assistant installed."""
import sys
from pathlib import Path

QW_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "qweather"
if str(QW_DIR) not in sys.path:
    sys.path.insert(0, str(QW_DIR))
