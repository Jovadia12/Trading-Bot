"""CLI: python -m lead_finder <command>

  serve        [--host 127.0.0.1] [--port 8060]
  init-db
  create-user  --firm "Firm name" --email user@firm.com [--name "Full Name"]   (password read from stdin/prompt)
"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import security
from .config import Settings
from .db import connect, init_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lead_finder")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8060)
    sub.add_parser("init-db")
    cu = sub.add_parser("create-user")
    cu.add_argument("--firm", required=True)
    cu.add_argument("--email", required=True)
    cu.add_argument("--name")
    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.cmd == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return 0

    conn = connect(settings.db_path)
    init_db(conn)
    if args.cmd == "init-db":
        print(f"Initialized {settings.db_path}")
        return 0
    if args.cmd == "create-user":
        password = sys.stdin.readline().rstrip("\n") if not sys.stdin.isatty() else getpass.getpass("Password: ")
        row = conn.execute("SELECT id FROM firms WHERE name = ?", (args.firm.strip(),)).fetchone()
        firm_id = row["id"] if row else security.create_firm(conn, args.firm)
        user_id = security.create_user(conn, firm_id, args.email, password, args.name)
        print(f"Created user {user_id} in firm {firm_id} ({args.firm})")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
