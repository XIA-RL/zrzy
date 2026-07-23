from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PIPELINE_MODE", "mock")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
r = client.post("/api/jobs", json={"text": "分析安吉县2023年生境质量"})
job_id = r.json()["id"]
for _ in range(30):
    job = client.get(f"/api/jobs/{job_id}").json()
    if job["status"] in ("done", "failed"):
        break
    time.sleep(0.2)

print("status:", job["status"])
print("steps:", len(job.get("steps", [])))
for s in job.get("steps", []):
    print(" -", s["id"], s["status"], s.get("message", "")[:40])
