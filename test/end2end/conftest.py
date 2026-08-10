"""Keep end-to-end tests optional for unit-test-only installations."""

collect_ignore_glob = []

try:
    import ovoscope  # noqa: F401
except ImportError:
    collect_ignore_glob = ["test_intents.py"]
