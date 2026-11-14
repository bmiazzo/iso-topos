# Idiomatic SOLID Patterns: Python & TypeScript/JS

Use language-native structural typing and functions before reaching for heavy class hierarchies.

---

## Python Patterns

### SRP + DIP: Separate I/O from Domain Logic with `Protocol`
**Before (coupled I/O and logic):**
```python
class AnalogAnalyzer:
    def run(self, site_id: str) -> float:
        resp = requests.get(f"https://api.example.com/sites/{site_id}")
        data = resp.json()
        score = (data["temp_k"] - 210) ** 2 + data["slope_deg"]
        with open(f"{site_id}.txt", "w") as f:
            f.write(str(score))
        return score
```

**After (cohesive, testable, inverted):**
```python
from typing import Protocol

class SiteDataSource(Protocol):
    def fetch_site(self, site_id: str) -> dict[str, float]: ...

def compute_similarity_score(site: dict[str, float]) -> float:
    return (site["temp_k"] - 210) ** 2 + site["slope_deg"]

def analyze_site(site_id: str, source: SiteDataSource) -> float:
    data = source.fetch_site(site_id)
    return compute_similarity_score(data)
```

### OCP: Strategy Mapping Instead of `if/elif` Chains
```python
from typing import Callable

MetricFn = Callable[[dict[str, float]], float]

METRICS: dict[str, MetricFn] = {
    "thermal": lambda d: abs(d["temp_k"] - 210.0),
    "terrain": lambda d: d["slope_deg"] * 0.5,
}

def score(metric_name: str, data: dict[str, float]) -> float:
    if metric_name not in METRICS:
        raise ValueError(f"Unknown metric: {metric_name}")
    return METRICS[metric_name](data)
```

---

## TypeScript / JavaScript Patterns

### ISP + DIP: Minimal Consumer Interfaces
**Before (depends on whole app store / concrete fetcher):**
```ts
async function loadMapLayer(layerId: string) {
  const res = await fetch(`/api/layers/${layerId}`);
  return res.json();
}
```

**After (depends only on what it needs):**
```ts
export interface LayerFetcher {
  getLayer(id: string): Promise<GeoJsonLayer>;
}

export async function loadMapLayer(
  layerId: string,
  fetcher: LayerFetcher,
): Promise<GeoJsonLayer> {
  return fetcher.getLayer(layerId);
}
```

### OCP + LSP: Exhaustive Discriminated Unions or Strategy Records
```ts
export type ExportFormat = "geojson" | "csv";

const EXPORTERS: Record<ExportFormat, (rows: SiteRecord[]) => string> = {
  geojson: (rows) => JSON.stringify({ type: "FeatureCollection", features: rows }),
  csv: (rows) => rows.map((r) => `${r.id},${r.score}`).join("\n"),
};

export function exportSites(format: ExportFormat, rows: SiteRecord[]): string {
  return EXPORTERS[format](rows);
}
```
