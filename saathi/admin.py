"""Admin CLI.

    python -m saathi.admin create-user officer1 --role officer     (prompts for password)
    python -m saathi.admin list-users
    python -m saathi.admin purge --days 30                          (data retention)
    python -m saathi.admin audit --case S1930-123456
"""
import argparse
import getpass

from .config import settings
from .db import DB
from .security import Auth


def main():
    ap = argparse.ArgumentParser(prog="python -m saathi.admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("username")
    c.add_argument("--role", default="officer", choices=["officer", "admin"])
    sub.add_parser("list-users")
    p = sub.add_parser("purge")
    p.add_argument("--days", type=int, default=30)
    a = sub.add_parser("audit")
    a.add_argument("--case", required=True)
    args = ap.parse_args()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = DB(str(settings.data_dir / "saathi.db"))
    if args.cmd == "create-user":
        pw = getpass.getpass("Password (min 10 chars): ")
        Auth(db).create_user(args.username, pw, args.role)
        print(f"created {args.role} {args.username}")
    elif args.cmd == "list-users":
        for r in db.all("SELECT username, role, created_at, disabled FROM users"):
            print(dict(r))
    elif args.cmd == "purge":
        print(f"deleted {db.purge_older_than(args.days)} cases older than {args.days} days")
    elif args.cmd == "audit":
        for r in db.audit_for(args.case):
            print(r)


if __name__ == "__main__":
    main()
