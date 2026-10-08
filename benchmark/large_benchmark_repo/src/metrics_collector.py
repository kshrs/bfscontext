"""Usage analytics and aggregation pipeline."""
from typing import Dict

class MetricsCollector:
    def __init__(self):
        self.counters = {}

    def increment(self, metric: str, count: int = 1) -> None:
        self.counters[metric] = self.counters.get(metric, 0) + count

    def report_all(self) -> Dict[str, int]:
        return dict(self.counters)
