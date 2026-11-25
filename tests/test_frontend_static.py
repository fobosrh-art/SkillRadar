"""Static regression guards for the React frontend (no browser needed)."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"


def test_no_expression_bodied_effects():
    """Regression: `useEffect(() => window.scrollTo(0, 0), ...)` returned the Promise that modern Chrome's
    scrollTo() yields; React called it as the cleanup on the next navigation and the app unmounted.
    Effects must use a block body (or return a cleanup function explicitly)."""
    offenders = []
    for f in SRC.rglob("*.tsx"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"use(Layout)?Effect\(\s*\(\)\s*=>\s*[^{\s]", line):
                offenders.append(f"{f.name}:{i}: {line.strip()}")
    assert offenders == [], offenders


def test_routes_are_wrapped_in_error_boundary():
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "ErrorBoundary" in app and "key={" in app
