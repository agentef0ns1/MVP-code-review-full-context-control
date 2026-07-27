from mcp.server.fastmcp import FastMCP

from mvp_memory.mcp_prompts import register_mcp_prompts


def test_register_audit_prompts():
    server = FastMCP("test-prompts")
    names = register_mcp_prompts(server)
    assert "audit-security-full" in names
    assert "audit-js-console-api" in names
    assert "guide-cline" in names
    assert "audit-quickstart" in names
    assert "audit-orchestration" in names
    assert len(names) >= 6
