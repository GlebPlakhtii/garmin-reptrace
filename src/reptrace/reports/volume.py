"""Read-only bridge to the dashboard's adjusted-volume calculation."""

import json
from pathlib import Path
import subprocess


def adjusted_sets(data):
    payload = {key: data[key] for key in ("sets", "recovery", "volumeSettings") if key in data}
    payload.setdefault("sets", [])
    try:
        result = subprocess.run(
            ["node", str(Path(__file__).with_suffix(".mjs"))],
            input=json.dumps(payload, allow_nan=False),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Adjusted-volume calculations unavailable; Node.js 22+ is required") from None
    if result.returncode:
        raise RuntimeError("Adjusted-volume calculation failed")
    return json.loads(result.stdout)
