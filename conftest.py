import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run optional sandbox integration tests (requires AT_API_KEY env var).",
    )
