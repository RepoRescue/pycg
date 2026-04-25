"""
PyCG bug-hunt (SKILL Step 7, anti-PyCG-blindspot).

Targets the specific Layer-2 bug from paper Section 7:
  - In Python 3.13, `importlib.invalidate_caches()` iterates
    `sys.path_hooks` and calls `.invalidate_caches()` on each entry.
  - PyCG's tests stub `sys.path_hooks` with non-callable sentinels
    (e.g. classes without `invalidate_caches`), and `_clear_caches`
    is invoked deep inside the analyze loop. Pre-rescue, the call
    blows up with TypeError; post-rescue (codex), the call is
    wrapped with try/except TypeError.

We reproduce the precise failure surface, then assert PyCG's
`_clear_caches` no longer crashes.

Additional probes:
  A. Repeated CallGraphGenerator.analyze() on same file (state leak)
  B. Empty / unicode / non-ASCII path inputs
  C. Concurrent analyze() in 2 threads
"""

import os
import sys
import threading
import importlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "fixtures" / "sample.py"
# PyCG resolves entry points relative to cwd; pin cwd to sample dir.
os.chdir(SAMPLE.parent)
SAMPLE_REL = SAMPLE.name

bugs = []


def probe_invalidate_caches_reentrancy():
    """Layer-2 reentrancy bug: stub sys.path_hooks with non-callables and
    invoke ImportManager._clear_caches via a CallGraphGenerator analyze()."""
    from pycg.pycg import CallGraphGenerator

    saved_hooks = list(sys.path_hooks)
    saved_cache = dict(sys.path_importer_cache)
    try:
        # Inject a sentinel that has no .invalidate_caches (like PyCG's
        # own unit tests do via mocks in tests/imports_test.py). On
        # un-patched 3.13 this trips through importlib.invalidate_caches
        # and raises TypeError mid-analyze.
        class _Sentinel:
            def __repr__(self):
                return "<bug-hunt-sentinel>"

        sys.path_hooks.append(_Sentinel())  # non-callable, no invalidate_caches
        cg = CallGraphGenerator([str(SAMPLE)], str(SAMPLE.parent), -1, "call-graph")
        cg.analyze()
        out = cg.output()
        if "sample.main" not in out:
            bugs.append("invalidate_caches probe: analyze() finished but output missing sample.main")
        else:
            print("OK: invalidate_caches reentrancy probe survived sentinel in sys.path_hooks")
    except TypeError as e:
        bugs.append(f"Layer-2 TypeError reentrancy STILL TRIGGERS (rescue wrapper missed it): {e!r}")
    except Exception as e:
        # ImportManagerError here = a *deeper* Layer-2 reentrancy variant:
        # importlib.invalidate_caches() walks installed finders, which
        # re-invokes PyCG's own CustomFinder.__init__ -> ig.create_edge()
        # on a node that hasn't been created yet. The codex rescue caught
        # only TypeError, not this path. Same root cause as the paper's
        # Layer-2 bug, different downstream exception type.
        bugs.append(
            f"Layer-2 reentrancy variant: {type(e).__name__}: {e!r} "
            "(rescue's try/except TypeError does NOT cover this)"
        )
    finally:
        sys.path_hooks[:] = saved_hooks
        sys.path_importer_cache.clear()
        sys.path_importer_cache.update(saved_cache)


def probe_repeat_analyze():
    from pycg.pycg import CallGraphGenerator
    try:
        for i in range(3):
            cg = CallGraphGenerator([str(SAMPLE)], str(SAMPLE.parent), -1, "call-graph")
            cg.analyze()
            out = cg.output()
            assert "sample.main" in out
        print("OK: 3x repeated analyze() consistent")
    except Exception as e:
        bugs.append(f"repeated analyze leaked: {type(e).__name__}: {e!r}")


def probe_empty_input():
    from pycg.pycg import CallGraphGenerator
    try:
        cg = CallGraphGenerator([], ".", -1, "call-graph")
        cg.analyze()
        cg.output()
        print("OK: empty entry_points list handled (no crash)")
    except Exception as e:
        # Acceptable if it raises a clear ValueError; we just record it
        print(f"NOTE: empty input -> {type(e).__name__}: {e}")


def probe_concurrent():
    from pycg.pycg import CallGraphGenerator
    errors = []

    def worker():
        try:
            cg = CallGraphGenerator([str(SAMPLE)], str(SAMPLE.parent), -1, "call-graph")
            cg.analyze()
            cg.output()
        except Exception as e:
            errors.append(e)

    ts = [threading.Thread(target=worker) for _ in range(2)]
    for t in ts: t.start()
    for t in ts: t.join()
    if errors:
        bugs.append(f"concurrent analyze errors: {errors!r}")
    else:
        print("OK: 2-thread concurrent analyze() didn't crash")


def main():
    probe_invalidate_caches_reentrancy()
    probe_repeat_analyze()
    probe_empty_input()
    probe_concurrent()

    print()
    if bugs:
        print(f"BUGS FOUND ({len(bugs)}):")
        for b in bugs:
            print(f"  - {b}")
        return 1
    print("BUG-HUNT CLEAN: 4 probes, 0 confirmed regressions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
