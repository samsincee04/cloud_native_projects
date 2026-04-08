"""Pytest configuration: add project root to Python path so 'src' can be imported."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
