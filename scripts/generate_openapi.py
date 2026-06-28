#!/usr/bin/env python3
"""Generate the final OpenAPI/Swagger spec for the AOP control-plane.

Usage:
    PYTHONPATH=control-plane:../HerdMaster/src \
    /tmp/aop-control-plane-venv/bin/python \
    scripts/generate_openapi.py [output_path]

Default output: docs/30-COMPONENTES/openapi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    output_path = Path(
        sys.argv[1] if len(sys.argv) > 1 else "docs/30-COMPONENTES/openapi.json"
    )

    from app.main import create_app

    app = create_app()
    spec = app.openapi()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    path_count = len(spec.get("paths", {}))
    schema_count = len(spec.get("components", {}).get("schemas", {}))
    print(f"OpenAPI spec written to {output_path}")
    print(f"  Paths:   {path_count}")
    print(f"  Schemas: {schema_count}")
    print(f"  Version: {spec.get('openapi', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
