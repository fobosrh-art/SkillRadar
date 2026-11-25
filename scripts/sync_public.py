"""Copy the publishable part of the private SkillRadar project into the public repository folder.

Safety rules (see docs/publishing.md):
  * ALLOWLIST only: a file is published only if it matches INCLUDE and not EXCLUDE. New folders are never published
    automatically - add them to INCLUDE on purpose.
  * Every file is scanned for secrets, personal data and local paths before anything is copied. Any finding stops the
    sync (exit code 1) unless that exact file/line was reviewed and listed in REVIEWED.
  * The script never commits or pushes. It prints `git status` of the public copy so the changes can be reviewed.

Usage (from the private project root):
  .venv\\Scripts\\python scripts\\sync_public.py --target ..\\SkillRadar-public            # dry run: scan + list
  .venv\\Scripts\\python scripts\\sync_public.py --target ..\\SkillRadar-public --apply    # copy into the public repo
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INCLUDE = [
    "README.md", "requirements.txt", "pytest.ini", ".env.example", ".gitignore", ".gitattributes",
    "setup.cmd", "start.cmd", "start-demo.cmd", "Dockerfile", "docker-compose.yml", ".dockerignore",
    "skillradar/**", "tests/**", "scripts/sync_public.py",
    "docs/*.md", "docs/screenshots/*.png", "docs/screenshots/README.md",
    "frontend/index.html", "frontend/package.json", "frontend/package-lock.json", "frontend/tsconfig*.json",
    "frontend/vite.config.ts", "frontend/tailwind.config.*", "frontend/postcss.config.*",
    "frontend/src/**", "frontend/public/**",
]
EXCLUDE = [
    "**/__pycache__/**", "*.pyc", "*.db", "*.db-*", "*.log", ".env", ".env.*.local",
    "docs/defense-demo.md",          # internal, Russian defense script
    "docs/vendor/**",                # third-party schema, redistribution terms unknown
    "data/**", "data-demo/**", ".venv/**", "frontend/node_modules/**", "frontend/dist/**", ".claude/**",
]

TEXT_SUFFIXES = {".py", ".md", ".txt", ".ts", ".tsx", ".json", ".cmd", ".yml", ".yaml", ".toml", ".ini", ".html",
                 ".css", ".js", ".cjs", ".mjs", ".csv", ".psv", ".sql", ".example", ""}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "anthropic.com", "localhost",
                         "users.noreply.github.com")
CHECKS = {
    "github token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "generic secret assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    "softon key value": re.compile(r"SOFTON_API_KEY\s*=\s*\S+"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "local user path": re.compile(r"(?i)[a-z]:[\\/]+users[\\/]+|/home/[a-z]"),
    "phone number": re.compile(r"(?<![\w.])\+?994[\s-]?\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"),
}

# Reviewed findings: (file glob, substring of the offending line). Keep this list short and explain each entry.
REVIEWED = [
    ("tests/*", ""),                   # tests contain deliberately fake e-mails/phones to prove redaction
    ("skillradar/transform/pii.py", ""),  # the redaction regexes themselves
    ("scripts/sync_public.py", ""),    # this scanner's own patterns
    ("docs/*.md", "SOFTON_API_KEY"),   # documentation mentions the variable name, never a value
    (".env.example", "SOFTON_API_KEY="),  # empty template value
    ("setup.cmd", "SOFTON_API_KEY=..."),  # instruction text, no value
]


def matches(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def selected_files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or matches(rel, EXCLUDE) or not matches(rel, INCLUDE):
            continue
        out.append(p)
    return out


def reviewed(rel: str, line: str) -> bool:
    return any(fnmatch.fnmatch(rel, g) and sub in line for g, sub in REVIEWED)


def scan(files: list[Path]) -> list[str]:
    findings = []
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if p.stat().st_size > 5_000_000:
            findings.append(f"{rel}: unexpectedly large text file ({p.stat().st_size} bytes)")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for no, line in enumerate(text.splitlines(), 1):
            hits = [name for name, rx in CHECKS.items() if rx.search(line)]
            hits += [f"e-mail {m}" for m in EMAIL.findall(line)
                     if not m.lower().endswith(ALLOWED_EMAIL_DOMAINS) and not re.match(r"^[\w-]+@\d", m)]
            if hits and not reviewed(rel, line):
                findings.append(f"{rel}:{no}: {', '.join(hits)}: {line.strip()[:120]}")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="folder of the public git repository")
    ap.add_argument("--apply", action="store_true", help="copy files (otherwise dry run)")
    a = ap.parse_args()
    target = Path(a.target).resolve()
    if target == ROOT or ROOT in target.parents:
        print("target must be outside the private project", file=sys.stderr)
        return 2

    files = selected_files()
    findings = scan(files)
    print(f"{len(files)} files selected by the allowlist")
    if findings:
        print("\nSECURITY SCAN FAILED - nothing was copied:")
        print("\n".join("  " + f for f in findings))
        return 1
    print("security scan: no findings")
    if not a.apply:
        for p in files:
            print("  " + p.relative_to(ROOT).as_posix())
        print("\nDry run only. Re-run with --apply to copy.")
        return 0

    if not (target / ".git").is_dir():
        print(f"{target} is not a git repository (run `git init` there first)", file=sys.stderr)
        return 2
    wanted = {p.relative_to(ROOT).as_posix() for p in files}
    for p in sorted(target.rglob("*"), reverse=True):        # remove files that are no longer published
        rel = p.relative_to(target).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if p.is_file() and rel not in wanted:
            p.unlink()
            print(f"  removed {rel}")
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    for p in files:
        dst = target / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
    print(f"copied {len(files)} files to {target}\n")
    subprocess.run(["git", "-C", str(target), "add", "-A", "--dry-run"], check=False)
    subprocess.run(["git", "-C", str(target), "status", "--short"], check=False)
    print("\nReview the changes above, then commit and push manually (see docs/publishing.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
