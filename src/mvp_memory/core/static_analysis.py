from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run_static_tools(
    target: Path,
    out: Path,
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    static_dir = out / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    target_s = str(target.resolve())
    out_s = str(out.resolve())

    for spec in tools:
        tool_id = spec["id"]
        cmd_name = spec.get("command", tool_id)
        if shutil.which(cmd_name) is None:
            results.append(
                {
                    "tool_id": tool_id,
                    "status": "skipped",
                    "reason": f"{cmd_name} not installed",
                }
            )
            continue
        args = [
            a.replace("{target}", target_s).replace("{output}", out_s)
            for a in spec.get("args", [])
        ]
        timeout = int(spec.get("timeout_sec", 300))
        out_file = spec.get("output_file", f"static/{tool_id}.txt")
        out_path = out / out_file
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if tool_id == "semgrep":
                proc = subprocess.run(
                    [cmd_name, *args],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=target_s,
                )
                text = proc.stdout or proc.stderr or ""
                out_path.write_text(text, encoding="utf-8")
                status = "ok" if proc.returncode in (0, 1) else "error"
            else:
                proc = subprocess.run(
                    [cmd_name, *args],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                status = "ok" if proc.returncode == 0 else "error"
                if not out_path.is_file() and proc.stdout:
                    out_path.write_text(proc.stdout, encoding="utf-8")
            results.append(
                {
                    "tool_id": tool_id,
                    "status": status,
                    "artifact": str(out_path),
                    "exit_code": proc.returncode,
                }
            )
        except subprocess.TimeoutExpired:
            results.append({"tool_id": tool_id, "status": "timeout"})
        except OSError as e:
            results.append({"tool_id": tool_id, "status": "error", "reason": str(e)})

    readme = static_dir / "README.md"
    lines = ["# Herramientas estáticas", ""]
    for r in results:
        lines.append(f"- **{r['tool_id']}**: {r['status']} — {r.get('artifact', r.get('reason', ''))}")
    lines.append("")
    lines.append("Triar y registrar con `memory_audit_record_finding`.")
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results
