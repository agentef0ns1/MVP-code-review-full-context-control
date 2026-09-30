from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _slug(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:40]
    return s or "finding"


def next_find_id(out: Path) -> tuple[str, int]:
    seq_path = out / ".finding_seq"
    n = 1
    if seq_path.is_file():
        try:
            n = int(seq_path.read_text().strip()) + 1
        except ValueError:
            n = 1
    seq_path.write_text(str(n), encoding="utf-8")
    return f"FIND-{n:03d}", n


def record_finding(
    out: Path,
    *,
    severity: str,
    title: str,
    description: str = "",
    cwe: str | None = None,
    file_path: str | None = None,
    line: int | None = None,
    poc_markdown: str = "",
    evidence: str = "",
) -> dict[str, Any]:
    find_id, _seq = next_find_id(out)
    slug = _slug(title)
    folder = out / "findings" / f"{find_id}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)

    informe = folder / "informe.md"
    informe.write_text(
        f"# {find_id}: {title}\n\n"
        f"- **Severidad:** {severity}\n"
        f"- **CWE:** {cwe or '—'}\n"
        f"- **Ubicación:** `{file_path or '—'}`"
        + (f":{line}" if line else "")
        + f"\n- **Generado:** {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## Descripción\n\n{description}\n\n"
        f"## Evidencia\n\n```\n{evidence[:8000]}\n```\n",
        encoding="utf-8",
    )
    if poc_markdown.strip():
        (folder / "poc.md").write_text(poc_markdown.strip() + "\n", encoding="utf-8")
        poc_rel = f"poc/{find_id}-{slug}/" if False else f"findings/{find_id}-{slug}/poc.md"
    else:
        poc_rel = "—"

    idx = out / "indice.md"
    if not idx.is_file():
        idx.write_text(
            "# Índice de hallazgos\n\n"
            "| ID | Severidad | Resumen | Informe | PoC | Estado |\n"
            "|----|-----------|---------|---------|-----|--------|\n",
            encoding="utf-8",
        )
    row = (
        f"| {find_id} | {severity} | {title[:80]} | "
        f"[informe](findings/{find_id}-{slug}/informe.md) | {poc_rel} | confirmado |\n"
    )
    with idx.open("a", encoding="utf-8") as f:
        f.write(row)

    return {
        "finding_id": find_id,
        "folder": str(folder),
        "informe": str(informe),
        "index": str(idx),
    }


def write_scan_index(out: Path, scans: list[dict[str, Any]]) -> str:
    path = out / "findings" / "00-scan-index.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Índice de escaneos rg (automático)",
        "",
        f"Generado: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| ID | Artefacto | Líneas |",
        "|----|-----------|--------|",
    ]
    for s in scans:
        lines.append(
            f"| {s.get('search_id', '?')} | `{s.get('artifact', '')}` | {s.get('line_count', '—')} |"
        )
    lines.extend(
        [
            "",
            "Siguiente paso: triar hits y registrar con `memory_audit_record_finding`.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def finalize_audit(out: Path) -> dict[str, Any]:
    findings_dir = out / "findings"
    find_folders = sorted(
        p for p in findings_dir.glob("FIND-*") if p.is_dir()
    )
    informes = list(findings_dir.glob("FIND-*/informe.md"))
    resumen = out / "RESUMEN-EJECUTIVO.md"
    body = [
        "# Resumen ejecutivo",
        "",
        f"**Findings en disco:** {len(find_folders)} carpetas FIND-*",
        f"**Informes:** {len(informes)}",
        "",
    ]
    for p in find_folders:
        first = (p / "informe.md").read_text(encoding="utf-8").split("\n", 3)
        title = first[0].replace("# ", "") if first else p.name
        body.append(f"- [{p.name}](findings/{p.name}/informe.md) — {title}")
    if len(find_folders) == 0:
        body.append(
            "\n⚠️ **Sin hallazgos persistidos.** El agente debe usar `memory_audit_record_finding` "
            "por cada issue; no basta con el resumen en el chat.\n"
        )
    incidentes = out / "INCIDENTES.md"
    body.extend(["", "## Pendiente de revisión", ""])
    if incidentes.is_file():
        body.append(
            "Los fallos de lectura o de scan están en [INCIDENTES.md](INCIDENTES.md)."
        )
        preview = incidentes.read_text(encoding="utf-8").splitlines()[:40]
        if preview:
            body.extend(["", *preview])
    else:
        body.append("No hay incidentes.")
    resumen.write_text("\n".join(body) + "\n", encoding="utf-8")
    return {
        "resumen_path": str(resumen),
        "finding_count": len(find_folders),
        "complete": len(find_folders) > 0,
    }
