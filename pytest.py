import os
import sys
import unittest


def _resolve_start_dir(path):
    if not path:
        return os.path.join("pycg", "tests")
    if os.path.exists(path):
        return path
    if path.rstrip("/\\") == "tests" and os.path.isdir(os.path.join("pycg", "tests")):
        return os.path.join("pycg", "tests")
    return path


def _iter_test_paths(argv):
    for arg in argv:
        if arg.startswith("-"):
            continue
        yield _resolve_start_dir(arg)


def main():
    paths = list(_iter_test_paths(sys.argv[1:])) or [os.path.join("pycg", "tests")]
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()

    for path in paths:
        if os.path.isdir(path):
            suite.addTests(loader.discover(path, pattern="*_test.py"))
        elif os.path.isfile(path):
            suite.addTests(
                loader.discover(os.path.dirname(path) or ".", pattern=os.path.basename(path))
            )
        else:
            raise SystemExit("ERROR: file or directory not found: {}".format(path))

    verbosity = 0 if "-q" in sys.argv[1:] else 1
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
