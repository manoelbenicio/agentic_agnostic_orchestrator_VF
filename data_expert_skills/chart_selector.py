#!/usr/bin/env python3
import json
CHART_MAP = {"comparison": "bar", "trend": "line", "distribution": "histogram", "relationship": "scatter", "composition": "pie"}
def suggest(purpose): return {"chart": CHART_MAP.get(purpose.lower(), "bar"), "alternatives": list(CHART_MAP.values())}
if __name__ == "__main__":
    import sys; print(json.dumps(suggest(sys.argv[1] if len(sys.argv)>1 else "comparison"), indent=2))
