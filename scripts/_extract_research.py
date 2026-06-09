"""One-shot extractor: parse the workflow output JSON and write the three docs."""

import json
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
OUT_DIR = Path(sys.argv[2])

raw = SRC.read_text(encoding="utf-8")

# The output file is JSONL with the last 'result' line containing the structured object.
# The format we got is: {"result": "<json string>", ...}  or a wrapped envelope.
# Try several extraction strategies.

# Strategy 1: try as plain JSON
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    # Strategy 2: JSONL — find the line that parses with our keys
    data = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Workflow result envelope often has {"type":"result","result":<obj>}
        if isinstance(obj, dict):
            if "archDoc" in obj or "roadmap" in obj:
                data = obj
                break
            if "result" in obj and isinstance(obj["result"], dict) and "archDoc" in obj["result"]:
                data = obj["result"]
                break
            if "result" in obj and isinstance(obj["result"], str):
                # result is a JSON string of the actual object
                try:
                    inner = json.loads(obj["result"])
                    if isinstance(inner, dict) and "archDoc" in inner:
                        data = inner
                        break
                except json.JSONDecodeError:
                    pass

if data is None:
    print("Could not parse as JSON", file=sys.stderr)
    sys.exit(2)

# The workflow envelope wraps the script return value under "result"
if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
    data = data["result"]


def write_doc(name: str, body: str | None) -> None:
    if not body:
        print(f"[skip] {name} empty")
        return
    # Decode HTML entities the workflow may have introduced
    body = (
        body.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    path = OUT_DIR / name
    path.write_text(body, encoding="utf-8")
    print(f"[ok] {name}: {len(body)} chars")


write_doc("ARCHITECTURE.md", data.get("archDoc"))
write_doc("ROADMAP.md", data.get("roadmap"))
write_doc("TECH_STACK.md", data.get("techstack"))
