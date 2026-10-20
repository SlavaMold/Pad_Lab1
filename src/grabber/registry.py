import json
import hashlib
from pathlib import Path

class Registry:
    def __init__(self, registry_path: str = "registry.json"):
        self.registry_path = Path(registry_path)
        self.data = self._load()

    def _load(self) -> dict:
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def is_new_or_changed(self, source_id: str, content: str) -> bool:
        new_hash = self.compute_hash(content)
        existing = self.data.get(source_id)
        if existing is None:
            return True  # источника ещё не было — новый
        return existing["content_hash"] != new_hash  # изменился ли контент

    def update(self, source_id: str, content: str, raw_path: str):
        self.data[source_id] = {
            "content_hash": self.compute_hash(content),
            "last_fetched": __import__("datetime").datetime.utcnow().isoformat(),
            "raw_path": raw_path,
        }