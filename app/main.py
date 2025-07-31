#!/usr/bin/env python3
"""
Math Knowledge Base - Main Application
Streamlit GUI for managing mathematical concepts and knowledge graphs.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import and run the Streamlit editor
from editor.editor_streamlit import *

if __name__ == "__main__":
    # This file serves as the entry point for the Streamlit app
    # The actual GUI is implemented in editor_streamlit.py
    pass 