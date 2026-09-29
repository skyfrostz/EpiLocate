"""Run as the site service account: python -m aid_site.admin create-or-reset USERNAME"""

import argparse
import getpass
import sys

from .db import create_or_reset_user, initialize


def main():
    parser = argparse.ArgumentParser(description="Create or reset a local site account")
    parser.add_argument("action", choices=["create-or-reset"])
    parser.add_argument("username")
    parser.add_argument("--password-stdin", action="store_true", help="For secure provisioning pipelines; do not pass a password as a CLI argument")
    args = parser.parse_args()
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("New password (min 16 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            parser.error("Passwords do not match")
    initialize()
    create_or_reset_user(args.username, password)
    print(f"Account {args.username!r} is ready; existing sessions were revoked if reset.")


if __name__ == "__main__":
    main()
