"""Export the OpenAPI document so the frontend can generate its types.

`npm run gen:api` turns this into `apps/web/src/api/schema.d.ts` with
openapi-typescript, so the two sides cannot drift: a route whose response model
changes breaks the frontend's typecheck rather than failing silently at runtime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.main import create_app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> int:
    schema = create_app().openapi()
    OUT.write_text(json.dumps(schema, indent=2) + "\n")
    paths = schema.get("paths", {})
    print(f"wrote {OUT.name}: {len(paths)} paths, {len(schema['components']['schemas'])} schemas")
    for path in sorted(paths):
        methods = ",".join(sorted(m.upper() for m in paths[path]))
        print(f"  {methods:20} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
