"""Serper search endpoint, using standard-library HTTP with a bounded timeout."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import SearchEvidence, finite
from .retrieval import SearchError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SerperSearch:
    def __init__(self, api_key: str, *, timeout: float = 20):
        if not api_key or not api_key.strip():
            raise ValueError("Set SERPER_API_KEY (or SEARCH_API) in the environment or .env")
        finite(timeout)
        if not 0 < timeout <= 60:
            raise ValueError("Search timeout must be in (0, 60] seconds")
        self._api_key = api_key.strip()
        self.timeout = timeout

    @classmethod
    def from_env(cls, env_file: str | Path = ".env", *, timeout: float = 20):
        # Literal KEY=VALUE loading: no interpolation, execution or environment mutation.
        values = {}
        path = Path(env_file)
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                key, separator, value = line.strip().partition("=")
                if separator and key.strip() in ("SERPER_API_KEY", "SEARCH_API"):
                    values[key.strip()] = value.strip().strip("\"'")
        key = (os.getenv("SERPER_API_KEY") or os.getenv("SEARCH_API")
               or values.get("SERPER_API_KEY") or values.get("SEARCH_API") or "")
        return cls(key, timeout=timeout)

    def search(self, query: str, *, limit: int = 8) -> list[SearchEvidence]:
        if not query.strip() or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("Supply a search query and 1–10 results")
        request = Request("https://google.serper.dev/search",
                          data=json.dumps({"q": query, "num": limit}).encode(),
                          headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
                          method="POST")
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise SearchError("Serper response exceeded the size limit")
            payload = json.loads(raw)
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise SearchError(f"Serper HTTP {code}; check credentials, credits, or rate limits") from None
        except (URLError, TimeoutError):
            raise SearchError("Serper connection failed or timed out") from None
        except (ValueError, UnicodeDecodeError):
            raise SearchError("Serper returned invalid JSON") from None
        if not isinstance(payload, dict) or "error" in payload or "message" in payload:
            raise SearchError("Serper returned an API error or unexpected response")
        if not isinstance(payload.get("organic"), list):
            raise SearchError("Serper response is missing organic results")
        evidence = []
        retrieved_at = datetime.now(timezone.utc).isoformat()
        for item in payload["organic"][:limit]:
            if not isinstance(item, dict):
                continue
            if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("title", "link", "snippet")):
                continue
            position = item.get("position")
            if isinstance(position, bool) or not isinstance(position, int) or position < 1:
                continue
            evidence.append(SearchEvidence(
                sha256(item["link"].encode()).hexdigest()[:20], item["title"], item["link"],
                item["snippet"], position, query, retrieved_at))
        return evidence
