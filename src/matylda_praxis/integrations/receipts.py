"""Provider receipts stored separately from the portable Praxis record."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    artifact_id: str
    provider: str
    model: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    trace_id: str | None = None


class ReceiptStore:
    """Append-only JSONL telemetry that is never required to decode domain state."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def append(self, receipt: ExecutionReceipt) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(receipt), ensure_ascii=True, sort_keys=True) + "\n")

    def list(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        return tuple(json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line)
