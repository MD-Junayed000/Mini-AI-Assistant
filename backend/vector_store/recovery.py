"""Auto-recovery for a corrupted ChromaDB persistent directory.

A Windows process killed mid-upsert can leave Chroma's HNSW files
half-written; the next access segfaults in Rust code Python can't catch.
``auto_recover_if_corrupt`` probes in an isolated subprocess and quarantines
the dir to ``.bak-<stamp>`` so the next ingest rebuilds from ``data/``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from backend.observability.logging_config import get_logger

log = get_logger("chroma.recovery")

# Subprocess script: probe chromadb without poisoning our process.
_PROBE_SCRIPT = (
    "import json, sys\n"
    "try:\n"
    "    import chromadb\n"
    "    c = chromadb.PersistentClient(path=sys.argv[1])\n"
    "    c.heartbeat()\n"
    "    print(json.dumps({'ok': True}))\n"
    "except BaseException as e:\n"
    "    print(json.dumps({'ok': False, 'err': '%s: %s' % (type(e).__name__, e)}))\n"
)


def _probe_chroma_isolated(persist_dir: Path, timeout: float = 15.0) -> tuple[bool, str | None]:
    """Spawn a child interpreter to probe chromadb. Returns (healthy, reason)."""
    if not persist_dir.exists():
        return True, None
    if not any(persist_dir.iterdir()):
        return True, None
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _PROBE_SCRIPT, str(persist_dir)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "ANONYMIZED_TELEMETRY": "False", "CHROMA_TELEMETRY_DISABLED": "True"},
        )
    except subprocess.TimeoutExpired:
        return False, f"chroma_probe_timeout_{int(timeout)}s"
    except FileNotFoundError as exc:
        return False, f"chroma_probe_no_python: {exc}"

    stdout = (proc.stdout or "").strip()
    if stdout.startswith("{"):
        try:
            payload = json.loads(stdout.splitlines()[-1])
            if payload.get("ok"):
                return True, None
            return False, payload.get("err", "chroma_probe_failed")
        except json.JSONDecodeError:
            pass

    stderr_first = next(
        (ln.strip() for ln in (proc.stderr or "").splitlines() if ln.strip()),
        f"chroma_probe_exitcode_{proc.returncode}",
    )
    return False, f"chroma_probe_native: {stderr_first[:160]}"


def auto_recover_if_corrupt(
    persist_dir: Path | str,
    *,
    timeout: float = 15.0,
    force: bool = False,
) -> bool:
    """Quarantine a corrupt Chroma directory. Returns True if a recovery action was taken.

    Move-aside only; the ``.bak-<UTC-stamp>`` suffix is preserved for inspection.
    Failures are logged, never raised. Pass ``force=True`` to quarantine unconditionally.
    """
    persist_dir = Path(persist_dir)
    if not persist_dir.exists():
        return False

    healthy, reason = _probe_chroma_isolated(persist_dir, timeout=timeout)
    if healthy and not force:
        return False

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    base_backup = persist_dir.with_name(f"{persist_dir.name}.bak-{stamp}")
    backup = base_backup
    suffix = 1
    while backup.exists():
        backup = base_backup.with_name(f"{base_backup.name}-{suffix}")
        suffix += 1
    log.warning(
        "chroma_auto_recovery_quarantine",
        reason=reason or "forced",
        source=str(persist_dir),
        backup=str(backup),
    )
    try:
        shutil.move(str(persist_dir), str(backup))
    except OSError as exc:
        log.warning("chroma_auto_recovery_move_failed_falling_back", error=str(exc))
        try:
            shutil.copytree(str(persist_dir), str(backup), dirs_exist_ok=False)
            shutil.rmtree(str(persist_dir), ignore_errors=True)
        except OSError as e2:
            log.error("chroma_auto_recovery_copytree_failed", error=str(e2))
            return False
    persist_dir.mkdir(parents=True, exist_ok=True)
    log.info(
        "chroma_auto_recovery_complete",
        backup=str(backup),
        next_step="next /ingest call rebuilds the collection from data/",
    )
    return True