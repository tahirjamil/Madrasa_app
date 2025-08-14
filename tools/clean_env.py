#!/usr/bin/env python3
# utils/clean_env.py
import sys
from pathlib import Path
import re

if len(sys.argv) < 2:
    print("Usage: python utils/clean_env.py /path/to/.env")
    sys.exit(2)

env_path = Path(sys.argv[1])
backup = env_path.with_suffix(env_path.suffix + '.bak')
backup.write_bytes(env_path.read_bytes())
print(f"Backup written to {backup}")

seen = {}
line_re = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$')

out_lines = []
for line in env_path.read_text().splitlines():
    m = line_re.match(line)
    if not m:
        out_lines.append(line)
        continue
    key, raw_val = m.group(1), m.group(2)
    val = raw_val.strip()
    # remove optional surrounding quotes
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val_unquoted = val[1:-1]
    else:
        val_unquoted = val

    if key not in seen:
        # keep first appearance, but if it's empty mark and allow later non-empty to replace
        seen[key] = val_unquoted
        out_lines.append(f"{key}={raw_val}")
    else:
        # if previous value was empty and this one is non-empty, replace the line in out_lines
        if (seen[key] == '' or seen[key] is None) and val_unquoted:
            # replace previous occurrence in out_lines (search from end)
            for i in range(len(out_lines)-1, -1, -1):
                if out_lines[i].lstrip().startswith(f"{key}="):
                    out_lines[i] = f"{key}={raw_val}"
                    seen[key] = val_unquoted
                    break
        else:
            # skip this duplicate
            print(f"Removing duplicate {key} (kept first occurrence)")

env_path.write_text("\n".join(out_lines) + "\n")
print("Cleaned .env written (duplicates removed).")
