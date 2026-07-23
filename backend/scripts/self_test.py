from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app


def main() -> None:
    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200, r.text

    r = client.post("/api/jobs", json={"text": "计算安吉县2023年生境质量和碳储量"})
    assert r.status_code == 200, r.text
    job = r.json()
    job_id = job["id"]

    deadline = time.time() + 10
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        job = r.json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.2)

    assert job["status"] == "done", job
    assert "result" in job and job["result"], job
    assert job.get("artifacts"), job

    print("OK")
    print("job_id:", job_id)
    print("stage:", job["stage"])
    print("artifacts:", job["artifacts"])


if __name__ == "__main__":
    main()
