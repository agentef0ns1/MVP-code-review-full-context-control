"""Profile merge and findings."""
from pathlib import Path

from mvp_memory.audit_profiles_loader import load_profile


def test_security_full_merges_searches():
    p = load_profile("security-full")
    ids = {s["id"] for s in p["searches"]}
    assert "secrets" in ids
    assert "window-dot" in ids
    assert "xss-dom" in ids
    assert "sqli-sql" in ids
    assert len(p["searches"]) >= 15


def test_record_finding(tmp_path):
    from mvp_memory.audit_findings import record_finding, finalize_audit

    out = tmp_path / "audit"
    out.mkdir()
    (out / "findings").mkdir()
    r = record_finding(
        out,
        severity="high",
        title="XSS test",
        cwe="CWE-79",
        file_path="init.js",
        line=40,
        description="innerHTML",
    )
    assert Path(r["informe"]).is_file()
    fin = finalize_audit(out)
    assert fin["finding_count"] >= 1
    assert (out / "RESUMEN-EJECUTIVO.md").is_file()
