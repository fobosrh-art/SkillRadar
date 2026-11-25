# Publishing updates to the public repository

The public repository (`https://github.com/fobosrh-art/SkillRadar`) is a **separate git repository with its own
history**. It is filled from the private working project only through `scripts/sync_public.py`, which copies an
explicit allowlist of files after a security scan. The private project, its history, its data and its `.env` are
never pushed.

```
C:\Projects\SkillRadar          private working project (own git history, real data, .env)   -> never pushed
C:\Projects\SkillRadar-public   public copy (fresh history, allowlisted files only)          -> origin = GitHub
```

## Update procedure (Windows, from the private project root)

```bat
:: 1. Make sure the project is healthy
.venv\Scripts\python -m pytest
cd frontend && npm run typecheck && npm run build && cd ..

:: 2. Dry run: security scan + list of files that would be published (nothing is copied)
.venv\Scripts\python scripts\sync_public.py --target ..\SkillRadar-public

:: 3. Copy into the public repository (stops if the scan finds anything)
.venv\Scripts\python scripts\sync_public.py --target ..\SkillRadar-public --apply

:: 4. Review exactly what changed
cd ..\SkillRadar-public
git status
git diff --stat
git diff

:: 5. Commit and push (normal push only)
git add -A
git commit -m "Describe the change"
git push origin main
```

The public repository commits with the GitHub no-reply identity configured in its local git config
(`git config user.email` inside `SkillRadar-public`), so no personal e-mail address is published.

## Rules

* **Never** use `git push --force` on the public repository. If history must be rewritten (for example after an
  accidental publication of a secret), stop, revoke the secret first, and decide explicitly.
* New folders or file types are not published until they are added to `INCLUDE` in `scripts/sync_public.py`.
  Review every allowlist change.
* If the scan reports a finding, fix the file. Add an entry to `REVIEWED` only for deliberate test fixtures or
  documentation, with a comment explaining why.
* Never publish: `.env`, `data/` (raw Softon data, snapshots, the SQLite warehouse, backups, logs), `data-demo/`, ESCO
  CSV files, `docs/vendor/`, `node_modules/`, `.venv/`, `frontend/dist/`.
* Screenshots must show the synthetic demo (`start-demo.cmd`), not real vacancies.
* If a secret is ever pushed: revoke or rotate it immediately (for the Softon key, in the Softon dashboard). Deleting
  the commit is not enough.
