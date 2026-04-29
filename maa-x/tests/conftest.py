"""pytest configuration for maa-x."""

import sys
from pathlib import Path

# Ensure maa_x is importable from the project root
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))