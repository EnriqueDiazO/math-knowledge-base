#!/usr/bin/env python3
"""
Math Knowledge Base GUI Launcher
Simple script to launch the Streamlit GUI with proper environment setup.
"""

import subprocess
import sys
import os
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import streamlit
        import pymongo
        import pandas
        import networkx
        import pyvis
        print("✅ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please install dependencies with: pip install -r requirements.txt")
        return False

def check_mongodb():
    """Check if MongoDB is running."""
    try:
        import pymongo
        client = pymongo.MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
        client.server_info()
        print("✅ MongoDB is running")
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("Please start MongoDB with: sudo systemctl start mongod")
        return False

def main():
    print("🧮 Math Knowledge Base GUI Launcher")
    print("=" * 40)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check MongoDB
    if not check_mongodb():
        print("\n⚠️  MongoDB is not running. The GUI will show connection errors.")
        print("   You can still explore the interface, but database operations will fail.")
        response = input("   Continue anyway? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            sys.exit(1)
    
    print("\n🚀 Launching Math Knowledge Base GUI...")
    print("   The application will open in your default web browser.")
    print("   Press Ctrl+C to stop the server.\n")
    
    # Launch Streamlit
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            "editor/editor_streamlit.py",
            "--server.port", "8501",
            "--server.address", "localhost"
        ])
    except KeyboardInterrupt:
        print("\n👋 GUI stopped by user")
    except Exception as e:
        print(f"\n❌ Error launching GUI: {e}")

if __name__ == "__main__":
    main() 