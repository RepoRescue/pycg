# PyCG Rescue Target — FastMCP Integration

This directory contains the **rescue validation target** for this repo.
The goal of the rescue is **not** to make PyCG's own unit tests pass —
it is to make PyCG work as an in-process FastMCP tool on
Python 3.13 + modern setuptools.

## Success Criterion

From the repo root, inside the provided `venv-t1`:

```bash
./venv-t1/bin/python rescue_validation/validate.py
```

Must exit `0` and print:

```
PASS: FastMCP-wrapped PyCG returned all expected edges
  sample.main -> sample.Foo.method
  sample.Foo.method -> sample.alpha
  sample.alpha -> sample.beta
```

## Current Failure (pre-rescue)

The script currently crashes with:

```
ModuleNotFoundError: No module named 'pkg_resources'
```

because `pycg/formats/fasten.py` unconditionally does
`from pkg_resources import Requirement`, and modern setuptools
(≥ 80) no longer ships `pkg_resources`. Depending on how much of the
`pycg.formats` surface you touch, you may also trip a second,
subtler bug involving PyCG's `ImportManager.install_hooks()` and
Python 3.12+'s lazy `importlib.metadata` loading.

## Rules

1. **Do not modify `rescue_validation/validate.py` or
   `rescue_validation/sample.py`.** They are the spec.
2. Do not `pip install` or `pip uninstall` anything. The `venv-t1`
   contents are frozen.
3. You may modify anything under `pycg/` (the source package).
4. After each edit, re-run `./venv-t1/bin/python rescue_validation/validate.py`
   to check progress.
5. Stop when the script exits 0.
