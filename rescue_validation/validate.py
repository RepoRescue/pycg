"""
FastMCP wrap validation for PyCG.

Spins up an in-process FastMCP server that exposes a `pycg_analyze`
tool backed by pycg.pycg.CallGraphGenerator and pycg.formats.Fasten,
then uses FastMCP's in-process client to invoke the tool against
sample.py and asserts the returned call graph contains the expected
edges:

    sample.main         -> sample.Foo.method
    sample.Foo.method   -> sample.alpha
    sample.alpha        -> sample.beta

Exit 0 on PASS, non-zero on any failure.

This file is the rescue target: after rescue, running

    python rescue_validation/validate.py

must exit 0 inside venv-t1 (Python 3.13 + fastmcp + latest setuptools).
Do NOT modify this file or sample.py.
"""

import asyncio
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "sample.py"

EXPECTED_EDGES = [
    ("sample.main", "sample.Foo.method"),
    ("sample.Foo.method", "sample.alpha"),
    ("sample.alpha", "sample.beta"),
]


def _build_server():
    from fastmcp import FastMCP

    # A realistic MCP wrapper exposes PyCG's multiple output formats,
    # so both the core generator and the fasten formatter are imported
    # at module setup time -- any reasonable integrator would write it
    # this way, and it forces every PyCG import path (including
    # pycg.formats.fasten) to load before the tool is callable.
    from pycg.pycg import CallGraphGenerator
    from pycg.formats import Fasten  # noqa: F401

    mcp = FastMCP("pycg-wrapper")

    @mcp.tool
    def pycg_analyze(file_path: str, fmt: str = "call-graph") -> dict:
        cg = CallGraphGenerator(
            [file_path], str(Path(file_path).parent), -1, fmt
        )
        cg.analyze()
        raw = cg.output()
        return {
            k: sorted(v) if isinstance(v, (set, list, tuple)) else v
            for k, v in raw.items()
        }

    return mcp


async def _run():
    from fastmcp import Client

    mcp = _build_server()
    async with Client(mcp) as client:
        result = await client.call_tool(
            "pycg_analyze", {"file_path": str(SAMPLE)}
        )

    cg = getattr(result, "data", None)
    if cg is None and hasattr(result, "content"):
        text = result.content[0].text if result.content else "{}"
        cg = json.loads(text)
    if cg is None:
        cg = result

    if not isinstance(cg, dict):
        print(f"FAIL: tool returned non-dict result: {type(cg).__name__}")
        print(repr(cg))
        return 2

    missing = []
    for caller, callee in EXPECTED_EDGES:
        callees = cg.get(caller)
        if callees is None or callee not in callees:
            missing.append(f"{caller} -> {callee}")

    if missing:
        print("FAIL: expected edges missing from call graph:")
        for edge in missing:
            print(f"  - {edge}")
        print("Returned call graph:")
        print(json.dumps(cg, indent=2))
        return 1

    print("PASS: FastMCP-wrapped PyCG returned all expected edges")
    for caller, callee in EXPECTED_EDGES:
        print(f"  {caller} -> {callee}")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception:  # noqa: BLE001
        print("FAIL: exception during MCP wrap test")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
