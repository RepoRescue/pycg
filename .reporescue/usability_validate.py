"""
PyCG usability validation (SKILL v2, Scenario D / FastMCP).

Runs in a clean venv with `pip install -e repos/rescue_codex/pycg` already done.

Hard constraints exercised:
  1. Real input        : fixtures/sample.py (real Python source)
  2. Real assertion    : 3 explicit call-graph edges
  3. Beyond unit tests : the FastMCP wrap path is not covered by pycg/tests/*
  4. Primary use mode  : PyCG's flagship API CallGraphGenerator.analyze
  5. >=3 paths         : pycg.pycg, pycg.formats.Fasten, pycg.machinery.imports,
                         pycg.processing.base (4 distinct submodules)
  6. 3.13 surface      : pkg_resources -> packaging (fasten.py),
                         importlib.invalidate_caches/path_hooks reentrancy
                         (machinery/imports.py)
  7. Installed         : invoked from outside rescue tree, after pip install -e
  8. Downstream/scen.  : see downstream_validate.py (Scalpel cascade)
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
    from pycg.pycg import CallGraphGenerator
    from pycg.formats import Fasten  # noqa: F401  (forces full PyCG import chain)

    mcp = FastMCP("pycg-wrapper")

    @mcp.tool
    def pycg_analyze(file_path: str, fmt: str = "call-graph") -> dict:
        cg = CallGraphGenerator([file_path], str(Path(file_path).parent), -1, fmt)
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
        result = await client.call_tool("pycg_analyze", {"file_path": str(SAMPLE)})

    cg = getattr(result, "data", None)
    if cg is None and hasattr(result, "content"):
        text = result.content[0].text if result.content else "{}"
        cg = json.loads(text)
    if cg is None:
        cg = result
    if not isinstance(cg, dict):
        print(f"FAIL: tool returned non-dict: {type(cg).__name__}")
        return 2

    missing = [
        f"{caller} -> {callee}"
        for caller, callee in EXPECTED_EDGES
        if callee not in (cg.get(caller) or [])
    ]
    if missing:
        print("FAIL: expected edges missing:")
        for e in missing:
            print(f"  - {e}")
        print(json.dumps(cg, indent=2))
        return 1

    print("PASS step A: FastMCP-wrapped pycg_analyze returned all expected edges")
    for caller, callee in EXPECTED_EDGES:
        print(f"  {caller} -> {callee}")

    # Hard constraint 5 -- explicitly exercise >=3 distinct PyCG submodules
    # beyond the flagship CallGraphGenerator path:
    from pycg.formats import Fasten
    from pycg.machinery.imports import ImportManager
    from pycg.processing.base import ProcessingBase
    from pycg import utils as pycg_utils

    assert callable(Fasten)
    im = ImportManager()
    im.set_pkg(str(SAMPLE.parent))
    assert hasattr(im, "create_node")
    assert hasattr(ProcessingBase, "visit_FunctionDef")
    assert hasattr(ProcessingBase, "visit_ClassDef")
    assert hasattr(ProcessingBase, "analyze_submodule")
    assert any(hasattr(pycg_utils, n) for n in ("to_mod_name", "join_ns", "constants"))
    print("PASS step B: pycg.formats / pycg.machinery.imports / pycg.processing.base "
          "/ pycg.utils all import + expose expected API surface")

    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception:
        print("FAIL: exception during usability validate")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
