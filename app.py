import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from app import build_ui
ui = build_ui()
ui.launch()