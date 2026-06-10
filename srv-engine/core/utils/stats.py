"""
In-memory request stats. Resets on process restart.
Bounded by MAX_LOG (oldest entries evicted), so memory cost is fixed.
"""

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional


MAX_LOG = 50
MAX_ERRORS = 20


class _Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._requests: deque = deque(maxlen=MAX_LOG)
        self._errors: deque = deque(maxlen=MAX_ERRORS)
        self._domain_counts: Dict[str, int] = {}
        self._endpoint_totals: Dict[str, Dict[str, float]] = {}
        self._total = 0
        self._last_request_iso: Optional[str] = None

    def record(self, path: str, method: str, status: int, ms: float, domain: Optional[str]) -> None:
        now_iso = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with self._lock:
            self._total += 1
            self._last_request_iso = now_iso
            self._requests.appendleft({
                "time": now_iso,
                "method": method,
                "endpoint": path,
                "domain": domain or "-",
                "status": status,
                "ms": round(ms, 1),
            })
            if domain:
                self._domain_counts[domain] = self._domain_counts.get(domain, 0) + 1
            agg = self._endpoint_totals.setdefault(path, {"count": 0, "total_ms": 0.0})
            agg["count"] += 1
            agg["total_ms"] += ms

    def record_error(self, path: str, message: str) -> None:
        with self._lock:
            self._errors.appendleft({
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "endpoint": path,
                "message": message[:200],
            })

    def snapshot(self) -> Dict:
        with self._lock:
            uptime_s = int(time.time() - self._started_at)
            avg = {
                path: round(agg["total_ms"] / agg["count"], 1)
                for path, agg in self._endpoint_totals.items()
                if agg["count"]
            }
            return {
                "uptime_seconds": uptime_s,
                "uptime_human": _human_uptime(uptime_s),
                "total_requests": self._total,
                "last_request": self._last_request_iso,
                "domain_counts": dict(self._domain_counts),
                "endpoint_avg_ms": avg,
                "recent_requests": list(self._requests),
                "errors": list(self._errors),
            }


def _human_uptime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m"
    d, h = divmod(h, 24)
    return f"{d}d {h}h"


stats = _Stats()
