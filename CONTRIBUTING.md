# Contributing

Contributions should keep the project small, explicit, testable, and honest about implemented capabilities.

1. Create a focused branch from `main`.
2. Keep changes scoped and avoid unrelated refactors.
3. Add or update tests for behavior changes.
4. Run `ruff check .`, the unit tests with coverage, and `python engine.py` before opening a pull request.
5. Never commit credentials, private data, or generated local artifacts.
6. In the pull request, explain what changed, why it changed, and how it was tested.

Changes that add external models or tools should preserve clear permission boundaries, failure handling, and human approval for high-impact actions.
