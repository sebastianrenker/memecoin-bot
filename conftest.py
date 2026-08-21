import os
import sys

# Ensure the project root is importable when running `pytest -q` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
