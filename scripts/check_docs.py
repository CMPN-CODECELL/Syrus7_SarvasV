"""Inventory tracked/local Markdown and check local links without network access."""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def inventory():
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    documents = sorted({path for path in paths if path.endswith(".md")})
    sources = {}
    for path in paths:
        file = ROOT / path
        if file.is_file() and file.suffix in {
            ".md",
            ".py",
            ".jsx",
            ".js",
            ".yml",
            ".yaml",
            ".toml",
        }:
            sources[path] = file.read_text(encoding="utf-8")
    broken = []
    for path in documents:
        if path not in sources:
            continue
        text = re.sub(r"```.*?```", "", sources[path], flags=re.S)
        for target in re.findall(r"\]\(([^\n]+?)\)", text):
            target = target.strip()
            target = (
                target[1 : target.index(">")]
                if target.startswith("<")
                else target.split(' "', 1)[0]
            )
            if re.match(r"(?:[a-zA-Z]+:|#)", target):
                continue
            target = unquote(target.split("#", 1)[0])
            if target and not ((ROOT / path).parent / target).exists():
                broken.append((path, target))
    return documents, sources, broken


if __name__ == "__main__":
    documents, sources, broken = inventory()
    for path in documents:
        incoming = [
            source
            for source, text in sources.items()
            if source != path and (path in text or f"]({Path(path).name})" in text)
        ]
        category = (
            "historical"
            if "/archive/" in path or "/progress/MEMBER_" in path
            else "candidate"
            if "member-" in path.lower() or "ROUND2_RESEARCH" in path
            else "active/reference"
        )
        print(
            f"{path} | {category} | references: {', '.join(incoming) or 'none found'}"
        )
    for path, target in broken:
        print(f"BROKEN: {path} -> {target}")
    print(f"Markdown files: {len(documents)}; broken local links: {len(broken)}")
    raise SystemExit(bool(broken))
