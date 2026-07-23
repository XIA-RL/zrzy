#!/usr/bin/env python3
"""Quick test: create job and poll until clip step finishes or fails."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "http://127.0.0.1:8000"


def main() -> int:
    h = httpx.get(f"{API}/health", timeout=10).json()
    print("health:", h)
    if not h.get("clip_script_exists"):
        print("FAIL: clip script missing")
        return 1

    r = httpx.post(
        f"{API}/api/jobs",
        json={"text": "分析安吉县2023年生境质量"},
        timeout=30,
    )
    r.raise_for_status()
    job_id = r.json()["id"]
    print("job_id:", job_id)

    for _ in range(120):
        job = httpx.get(f"{API}/api/jobs/{job_id}", timeout=10).json()
        clip = next((s for s in job.get("steps", []) if s["id"] == "clip"), None)
        if clip:
            print("clip:", clip["status"], (clip.get("message") or "")[:120])
        if job["status"] in ("done", "failed"):
            print("final:", job["status"])
            if job.get("error"):
                print("error:", job["error"][:500])
            return 0 if job["status"] == "done" else 1
        if clip and clip["status"] in ("done", "failed"):
            return 0 if clip["status"] == "done" else 1
        time.sleep(2)

    print("timeout")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
