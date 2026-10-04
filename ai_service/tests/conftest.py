import sys
from pathlib import Path

# main.py и код AI-команды лежат в корне ai_service/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
