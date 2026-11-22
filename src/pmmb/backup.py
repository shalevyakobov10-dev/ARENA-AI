"""
גיבוי חם ובטוח של SQLite — בלי לסגור את הבוט.

למה לא cp? בזמן שהבוט כותב ל-DB, העתקה רגילה עלולה ליצור קובץ פגום.
`sqlite3.Connection.backup()` מעתיק snapshot עקבי ואז מאמת integrity_check.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class BackupResult:
    path: Path
    size_bytes: int
    ok: bool
    removed: int = 0


def backup_db(
    db_path: str | Path,
    backups_dir: str | Path = "backups",
    *,
    keep: int = 14,
) -> BackupResult:
    src_path = Path(db_path)
    if not src_path.exists():
        raise FileNotFoundError(f"קובץ DB לא קיים: {src_path}")

    out_dir = Path(backups_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    dst_path = out_dir / f"{src_path.stem}-{stamp}.db"

    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
        check = dst.execute("PRAGMA integrity_check").fetchone()
        ok = bool(check and str(check[0]).lower() == "ok")
    finally:
        dst.close()
        src.close()

    if not ok:
        dst_path.unlink(missing_ok=True)
        raise RuntimeError("גיבוי ה-DB נכשל בבדיקת שלמות (integrity_check)")

    # ניקוי גיבויים ישנים — שומרים את `keep` החדשים ביותר
    removed = 0
    if keep > 0:
        existing = sorted(
            out_dir.glob(f"{src_path.stem}-*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in existing[keep:]:
            old.unlink(missing_ok=True)
            removed += 1

    return BackupResult(path=dst_path, size_bytes=dst_path.stat().st_size,
                        ok=True, removed=removed)
