from dan.core.pathlib import Path


DAN_PATH = Path.home() / ".dan"
DAN_PATH.mkdir(exist_ok=True)
