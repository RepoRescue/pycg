"""
PyCG downstream cascade validation (Path A).

Scalpel is a real, published static-analysis library whose `call_graph`
subpackage is a thin wrapper around PyCG's `CallGraphGenerator`. Before
the rescue, importing `scalpel.call_graph.pycg` triggers the full PyCG
import chain and crashes on Python 3.13 (pkg_resources gone, plus the
invalidate_caches/path_hooks reentrancy).

This script proves PyCG's rescue propagates: with the rescued PyCG
installed and Scalpel's source on PYTHONPATH, FastMCP-wrapping
`scalpel.call_graph.pycg.CallGraphGenerator` succeeds and returns the
same expected call-graph edges. NO Scalpel source is modified.
"""

import asyncio
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "fixtures" / "sample.py"

EXPECTED_EDGES = [
    ("sample.main", "sample.Foo.method"),
    ("sample.Foo.method", "sample.alpha"),
    ("sample.alpha", "sample.beta"),
]


def _build_server():
    from fastmcp import FastMCP
    from scalpel.call_graph.pycg import CallGraphGenerator  # downstream entry

    mcp = FastMCP("scalpel-pycg-wrapper")

    @mcp.tool
    def scalpel_analyze(file_path: str) -> dict:
        cg = CallGraphGenerator([file_path], str(Path(file_path).parent), -1, "call-graph")
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
        result = await client.call_tool("scalpel_analyze", {"file_path": str(SAMPLE)})

    cg = getattr(result, "data", None)
    if cg is None and hasattr(result, "content"):
        text = result.content[0].text if result.content else "{}"
        cg = json.loads(text)
    if not isinstance(cg, dict):
        print(f"FAIL: tool returned non-dict: {type(cg).__name__}")
        return 2

    missing = [
        f"{caller} -> {callee}"
        for caller, callee in EXPECTED_EDGES
        if callee not in (cg.get(caller) or [])
    ]
    if missing:
        print("FAIL: expected edges missing from Scalpel cascade:")
        for e in missing:
            print(f"  - {e}")
        print(json.dumps(cg, indent=2))
        return 1

    print("PASS: Scalpel.call_graph.pycg cascade returned all expected edges")
    for caller, callee in EXPECTED_EDGES:
        print(f"  {caller} -> {callee}")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception:
        print("FAIL: exception during downstream cascade")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
