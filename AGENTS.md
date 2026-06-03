# This is NOT the Next.js you know

When we build the Plan B web wrapper (`web/` directory), it will use a version of Next.js with breaking changes from training-data defaults — APIs, conventions, and file structure may all differ. Before writing any Next.js code, read the relevant guide in `web/node_modules/next/dist/docs/` and heed deprecation notices.

This instruction is inherited from the parent `nectar-viz` project where the same Next.js version is used. The constraint applies once we initialise the `web/` Next.js project.

For the Python engine (`lighting-engine/`), no special Next.js concerns apply. Follow standard Python 3.11+ conventions, use uv, pytest, ruff, pyright as configured in `pyproject.toml`.
