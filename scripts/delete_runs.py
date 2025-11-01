"""
Delete all previous scan runs and related data from the database.

Usage:
    python scripts/delete_runs.py

This script deletes all records from run, candidate, feature, and eval_outcome tables.
"""

import os
import sys

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except ImportError:
    print("python-dotenv not installed. Run 'pip install python-dotenv' in your .venv.")
    sys.exit(1)

# Load .env file automatically
load_dotenv()
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    print("DB_URL not set in environment. Please set it in your .env file.")
    sys.exit(1)

engine = create_engine(DB_URL)


def delete_runs():
    with engine.begin() as conn:
        print("Deleting all eval_outcome records...")
        conn.execute(text("DELETE FROM eval_outcome"))
        print("Deleting all candidate records...")
        conn.execute(text("DELETE FROM candidate"))
        print("Deleting all feature records...")
        conn.execute(text("DELETE FROM feature"))
        print("Deleting all run records...")
        conn.execute(text("DELETE FROM run"))
    print("All previous runs and related data deleted.")


if __name__ == "__main__":
    delete_runs()
