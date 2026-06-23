#!/usr/bin/env python3
"""Commit/push web code to GitHub, then pull and redeploy on the cloud server.

Usage:
  python scripts/deploy_and_push.py
  python scripts/deploy_and_push.py --message "update web" --server 47.82.216.111
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd=ROOT, check=True):
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), text=True)
    if check and proc.returncode:
        raise SystemExit(proc.returncode)
    return proc.returncode


def remote_run(host, username, password, command):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password, timeout=20, banner_timeout=20, auth_timeout=20)
    chan = client.get_transport().open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(command)
    while True:
        if chan.recv_ready():
            sys.stdout.write(chan.recv(8192).decode("utf-8", errors="replace"))
            sys.stdout.flush()
        if chan.exit_status_ready():
            while chan.recv_ready():
                sys.stdout.write(chan.recv(8192).decode("utf-8", errors="replace"))
            code = chan.recv_exit_status()
            client.close()
            if code:
                raise SystemExit(code)
            return
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="https://github.com/resign13/video.git")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--message", default="update web app")
    parser.add_argument("--server", default="47.82.216.111")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="Caihanlin1")
    parser.add_argument("--app-dir", default="/opt/video")
    args = parser.parse_args()

    run(["git", "checkout", "-B", args.branch])
    run(["git", "remote", "remove", "origin"], check=False)
    run(["git", "remote", "add", "origin", args.repo])
    run(["git", "add", "."])
    if run(["git", "diff", "--cached", "--quiet"], check=False) != 0:
        run(["git", "-c", "user.name=Codex Deploy", "-c", "user.email=codex@local", "commit", "-m", args.message])
    else:
        print("No local changes to commit.")
    run(["git", "push", "-u", "origin", args.branch])

    deploy_cmd = (
        f"set -e; "
        f"if [ ! -d '{args.app_dir}/.git' ]; then rm -rf '{args.app_dir}'; git clone '{args.repo}' '{args.app_dir}'; "
        f"else cd '{args.app_dir}' && git fetch origin {args.branch} && git reset --hard origin/{args.branch}; fi; "
        f"cd '{args.app_dir}' && bash scripts/server_deploy.sh"
    )
    remote_run(args.server, args.user, args.password, deploy_cmd)
    print("Deploy complete.")


if __name__ == "__main__":
    main()
