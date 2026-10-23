"""Verify a successful authenticated scrape and the provisioned Grafana dashboard."""
import base64
import json
from pathlib import Path
import time
import urllib.request

values = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines()
              if "=" in line and not line.startswith("#"))
authorization = "Basic " + base64.b64encode(("admin:" + values["APP_TOKEN"]).encode()).decode()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        with opener.open('http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22vmerger%22%7D', timeout=3) as r:
            results = json.load(r)["data"]["result"]
        request = urllib.request.Request('http://127.0.0.1:3000/api/dashboards/uid/vmerger-operations',
                                         headers={"Authorization": authorization})
        with opener.open(request, timeout=3) as r:
            dashboard = json.load(r)
        if results and all(row["value"][1] == "1" for row in results) and len(dashboard["dashboard"]["panels"]) == 4:
            print("Authenticated Prometheus scrape and four-panel Grafana dashboard verified")
            break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit("Monitoring did not become ready within 60 seconds")
