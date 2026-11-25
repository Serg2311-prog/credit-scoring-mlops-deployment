"""One-shot sanitation for results/block8 evidence (encoding + path de-ID)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(".").resolve()
BLOCK8 = ROOT / "results" / "block8"
RAW_BACKUP = BLOCK8 / "_raw_encoding_backup"

ROOT_STR = str(ROOT)
ROOT_FORWARD = ROOT_STR.replace("\\", "/")


def detect_and_decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16").lstrip("\ufeff"), "utf-16-bom"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-bom"
    if len(raw) >= 4 and raw.count(b"\x00") > max(10, len(raw) // 5):
        try:
            return raw.decode("utf-16-le").lstrip("\ufeff"), "utf-16-le-heuristic"
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace").lstrip("\ufeff"), "utf-8"


def _to_repo_relative(path_str: str) -> str | None:
    """If path_str is under ROOT (any separators), return repo-relative posix path."""
    cleaned = path_str.strip().strip("\"'")
    if not cleaned:
        return None
    # Normalize common prefixes
    candidates = [cleaned, cleaned.replace("\\", "/"), cleaned.replace("/", "\\")]
    for cand in candidates:
        try:
            p = Path(cand)
            if not p.is_absolute():
                # Already relative — normalize slashes only
                if cand.startswith("./") or cand.startswith(".\\"):
                    return cand.replace("\\", "/")
                # bare relative like artifacts/...
                if not re.match(r"^[A-Za-z]:|^/|^\\\\", cand):
                    return cand.replace("\\", "/")
                continue
            resolved = p.resolve()
            try:
                rel = resolved.relative_to(ROOT)
                return rel.as_posix()
            except ValueError:
                continue
        except (OSError, RuntimeError, ValueError):
            continue
    # String-prefix fallback (path may not exist on disk)
    norms = [
        (cleaned, ROOT_STR, "\\"),
        (cleaned.replace("/", "\\"), ROOT_STR, "\\"),
        (cleaned.replace("\\", "/"), ROOT_FORWARD, "/"),
    ]
    for value, root, sep in norms:
        if value.lower().startswith(root.lower()):
            rem = value[len(root) :].lstrip("\\/")
            return rem.replace("\\", "/") if rem else "."
    return None


def sanitize_string(value: str) -> tuple[str, int]:
    """Relativize project paths; redact other absolute local paths."""
    hits = 0
    out = value

    # 1) Direct project-root replacement (spaces / Cyrillic safe)
    for root in (ROOT_STR, ROOT_FORWARD):
        if root and root in out:
            count = out.count(root)
            out = out.replace(root, ".")
            hits += count
    out = out.replace(".\\", "./")

    # 2) Whole-value absolute path (JSON string fields)
    stripped = out.strip().strip("\"'")
    if "\n" not in out and re.match(
        r"^[A-Za-z]:[\\/]|^/mnt/|^/home/|^/Users/|^/tmp/|^\\\\",
        stripped,
    ):
        rel2 = _to_repo_relative(stripped)
        if rel2 is not None:
            hits += 1
            return rel2, hits
        hits += 1
        return "<REDACTED_PATH>", hits

    # 3) Embedded absolute paths in logs / pytest / PowerShell
    win_pat = re.compile(r"(?P<p>[A-Za-z]:(?:\\+|/)(?:[^\\\"'\n\r|<>]+))")
    unix_pat = re.compile(
        r"(?P<p>/(?:mnt/[a-zA-Z]|home|Users|tmp|var|opt|usr)/[^\s\"'<>|]+)"
    )
    esc_pat = re.compile(r"(?P<p>[A-Za-z]:(?:\\\\[^\\\"'\n]+)+)")

    def repl(m: re.Match[str]) -> str:
        nonlocal hits
        raw_path = m.group("p")
        trimmed = raw_path.rstrip(").,]}")
        suffix = raw_path[len(trimmed) :]
        for attempt in (
            trimmed.replace("\\\\", "\\"),
            trimmed,
            trimmed.replace("/", "\\"),
        ):
            rel_p = _to_repo_relative(attempt)
            if rel_p is not None:
                hits += 1
                return rel_p + suffix
        hits += 1
        return "<REDACTED_PATH>" + suffix

    out2 = esc_pat.sub(repl, out)
    out2 = win_pat.sub(repl, out2)
    out2 = unix_pat.sub(repl, out2)
    return out2, hits


def walk_sanitize(obj: Any) -> tuple[Any, int]:
    hits = 0
    if isinstance(obj, str):
        return sanitize_string(obj)
    if isinstance(obj, list):
        out = []
        for item in obj:
            ni, h = walk_sanitize(item)
            hits += h
            out.append(ni)
        return out, hits
    if isinstance(obj, dict):
        out_d = {}
        for k, v in obj.items():
            nk, hk = sanitize_string(k) if isinstance(k, str) else (k, 0)
            nv, hv = walk_sanitize(v)
            hits += hk + hv
            out_d[nk] = nv
        return out_d, hits
    return obj, 0


def write_utf8(path: Path, text: str) -> None:
    text = text.lstrip("\ufeff")
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_bytes(text.encode("utf-8"))


def validate_json(text: str) -> str:
    try:
        json.loads(text)
        return "ok"
    except json.JSONDecodeError as exc:
        return f"fail: {exc}"


def validate_yaml(text: str) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        return "skip-no-pyyaml"
    try:
        list(yaml.safe_load_all(text))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"fail: {exc}"


def restore_from_backup_if_needed(*, force: bool = False) -> None:
    """Restore published files from .orig backups before re-sanitizing."""
    if not RAW_BACKUP.is_dir():
        return
    for backup in RAW_BACKUP.glob("*.orig"):
        name = backup.name[: -len(".orig")]
        # drift__demo_cli.txt.orig -> drift/demo_cli.txt
        rel = name.replace("__", "/")
        target = BLOCK8 / rel
        if target.exists() and not force:
            # Keep existing published file; backups remain as original proof.
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(backup.read_bytes())


def main() -> int:
    import sys

    force = "--force-restore" in sys.argv
    restore_from_backup_if_needed(force=force)

    converted: list[dict] = []
    deidentified: list[str] = []
    json_results: dict[str, str] = {}
    yaml_results: dict[str, str] = {}
    utf16_converted = 0
    bom8_converted = 0
    path_hits_total = 0

    RAW_BACKUP.mkdir(parents=True, exist_ok=True)

    for path in sorted(BLOCK8.rglob("*")):
        if not path.is_file():
            continue
        if RAW_BACKUP in path.parents or path.parent == RAW_BACKUP:
            continue
        if path.name in {"EVIDENCE_SANITATION.md", "sanitation_summary.json"}:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".pt", ".onnx", ".joblib"}:
            continue

        raw = path.read_bytes()
        text, enc = detect_and_decode(raw)
        original_sha = hashlib.sha256(raw).hexdigest()
        need_encoding = enc != "utf-8"
        hits = 0
        new_text = text

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(text)
                data2, hits = walk_sanitize(data)
                new_text = json.dumps(data2, indent=2, ensure_ascii=False) + "\n"
            except json.JSONDecodeError:
                new_text, hits = sanitize_string(text)
                if not new_text.endswith("\n"):
                    new_text += "\n"
        else:
            new_text, hits = sanitize_string(text)
            if new_text and not new_text.endswith("\n"):
                new_text += "\n"

        content_changed = new_text != text.lstrip("\ufeff")
        if need_encoding or content_changed or hits:
            rel = path.relative_to(BLOCK8)
            backup = RAW_BACKUP / (
                str(rel).replace("\\", "__").replace("/", "__") + ".orig"
            )
            if not backup.exists():
                backup.write_bytes(raw)
            write_utf8(path, new_text)
            rel_s = str(path.relative_to(ROOT)).replace("\\", "/")
            if need_encoding:
                if "utf-16" in enc:
                    utf16_converted += 1
                if enc == "utf-8-bom":
                    bom8_converted += 1
                converted.append(
                    {
                        "path": rel_s,
                        "from_encoding": enc,
                        "original_sha256": original_sha,
                        "backup": str(backup.relative_to(ROOT)).replace("\\", "/"),
                    }
                )
            if hits:
                deidentified.append(rel_s)
            path_hits_total += hits

        final = path.read_text(encoding="utf-8")
        rel_s = str(path.relative_to(ROOT)).replace("\\", "/")
        if path.suffix.lower() == ".json":
            json_results[rel_s] = validate_json(final)
        if path.suffix.lower() in {".yml", ".yaml"}:
            yaml_results[rel_s] = validate_yaml(final)

    remaining: list[list[str]] = []
    for path in sorted(BLOCK8.rglob("*")):
        if not path.is_file():
            continue
        if RAW_BACKUP in path.parents or path.parent == RAW_BACKUP:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".pt", ".onnx", ".joblib"}:
            continue
        raw = path.read_bytes()
        if b"\x00" in raw[:100]:
            remaining.append(
                [str(path.relative_to(ROOT)).replace("\\", "/"), "still-utf16"]
            )
            continue
        if raw.startswith(b"\xef\xbb\xbf"):
            remaining.append(
                [str(path.relative_to(ROOT)).replace("\\", "/"), "utf8-bom"]
            )
            continue
        text = raw.decode("utf-8", errors="replace")
        if ROOT_STR in text or ROOT_FORWARD in text:
            remaining.append(
                [
                    str(path.relative_to(ROOT)).replace("\\", "/"),
                    "project-root-still-present",
                ]
            )
            continue
        if re.search(
            r"(?i)C:\\\\Users\\\\Sergey|C:/Users/Sergey|/Users/Sergey|"
            r"\\\\Users\\\\Sergey",
            text,
        ):
            remaining.append(
                [
                    str(path.relative_to(ROOT)).replace("\\", "/"),
                    "username-path-remnant",
                ]
            )
        if re.search(r"(?i)Documents\\\\Личное|Documents/Личное", text):
            remaining.append(
                [
                    str(path.relative_to(ROOT)).replace("\\", "/"),
                    "cyrillic-personal-folder",
                ]
            )

    summary = {
        "utf16_converted": utf16_converted,
        "utf8_bom_converted": bom8_converted,
        "encoding_converted_total": len(converted),
        "deidentified_files": sorted(set(deidentified)),
        "deidentified_count": len(set(deidentified)),
        "path_replacements_total": path_hits_total,
        "converted": converted,
        "json_validation": json_results,
        "yaml_validation": yaml_results,
        "json_fail": [k for k, v in json_results.items() if v != "ok"],
        "yaml_fail": [k for k, v in yaml_results.items() if v != "ok"],
        "remaining_issues": remaining,
        "note": (
            "Original bytes for encoding-converted files are under "
            "results/block8/_raw_encoding_backup/*.orig with SHA256 in "
            "converted[].original_sha256"
        ),
    }
    (BLOCK8 / "sanitation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "encoding_converted_total": len(converted),
                "utf16_converted": utf16_converted,
                "utf8_bom_converted": bom8_converted,
                "deidentified": len(set(deidentified)),
                "json_fail": summary["json_fail"],
                "yaml_fail": summary["yaml_fail"],
                "remaining_n": len(remaining),
                "remaining_sample": remaining[:20],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if not remaining and not summary["json_fail"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
