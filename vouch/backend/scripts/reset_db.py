"""
Delete and rebuild the database from scratch.

Why this exists: SQLModel's create_all() adds missing TABLES but never ALTERs an existing one, so any
change to a model's columns leaves a stale schema behind and you get `OperationalError: no such
column` at request time. Deleting the file is the fix, and having it as one command means nobody has
to remember where the file lives.

    python -m scripts.reset_db          (from backend/)
    python -m scripts.reset_db --seed   (and reseed the demo data)

Note the difference from the API's POST /demo/reset: that one clears the demo's *rows* while the
server keeps running, which is what you want between rehearsals. This one rebuilds the *schema*, which
is what you want after changing models.py.
"""

from __future__ import annotations

import argparse
import sys

from app.config import DB_PATH, settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", action="store_true", help="reseed the demo data afterwards")
    args = parser.parse_args(argv)

    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except PermissionError:
            sys.exit(f"{DB_PATH} is in use - stop uvicorn first, then run this again.")
        print(f"deleted  {DB_PATH}")
    else:
        print(f"no database at {DB_PATH} (nothing to delete)")

    # Imported after the delete so the engine binds to a fresh file.
    from app.db import init_db

    init_db()
    print(f"created  {settings.database_url}")

    if args.seed:
        from scripts.seed import main as seed

        print()
        # Explicit empty argv: seed.main() parses its own flags, and without this it would read
        # OUR command line and choke on --seed.
        seed([])


if __name__ == "__main__":
    main()
