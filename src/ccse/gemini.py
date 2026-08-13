"""Gemini adapter: ~/.gemini/.env GEMINI_MODEL / base_url / api_key."""
from __future__ import annotations

from . import config
from .registry import (KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, Adapter, Slot,
                       register)

_ENV = {
    "model": "GEMINI_MODEL",
    "base_url": "GOOGLE_GEMINI_BASE_URL",
    "api_key": "GEMINI_API_KEY",
}


@register
class GeminiAdapter:
    id = "gemini"
    name = "Gemini CLI"
    primary = "gemini.model"
    path = config.HOME / ".gemini" / ".env"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _env(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in self.path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v
        return out

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        e = self._env()
        out = []
        for kind, label in ((KIND_MODEL, "model"),
                            (KIND_BASE_URL, "base_url"),
                            (KIND_API_KEY, "api_key")):
            var = _ENV[label]
            cur = e.get(var)
            if cur == "":
                cur = None
            out.append(Slot(key=f"{self.id}.{label}", label=f"{label} ({var})",
                            current=cur, kind=kind))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        relevant = {k[len("gemini."):]: v for k, v in assignments.items()
                    if k.startswith("gemini.")}
        if not relevant or not self.available:
            return []
        kv = self._env()
        diffs: list[str] = []
        for label, var in _ENV.items():
            if label not in relevant:
                continue
            old = kv.get(var)
            if old == relevant[label]:
                continue
            diffs.append(f"  {var}: {old!r} -> {relevant[label]!r}")
            if not dry:
                kv[var] = relevant[label]
        if not diffs:
            return []
        if not dry:
            lines = [f"{k}={v}" for k, v in kv.items()]
            text = "\n".join(lines) + "\n"
            config.write_text_atomic(self.path, text)
        return diffs

    def probe(self, timeout: int = 8) -> tuple[str, str]:
        """Gemini CLI speaks native generateContent, not OpenAI /models, so the
        default probe can't judge it. POST a trivial request to the configured
        endpoint; an error payload (e.g. protocol/credential mismatch) is FAIL."""
        import json
        import socket
        import ssl
        import urllib.error
        import urllib.request
        from urllib.parse import quote

        e = self._env()
        base, model, key = e.get("GOOGLE_GEMINI_BASE_URL"), e.get("GEMINI_MODEL"), \
            e.get("GEMINI_API_KEY")
        if not base or not model:
            return ("SKIP", "no base_url/model configured")
        url = base.rstrip("/") + "/v1beta/models/" + quote(model) + ":generateContent"
        payload = json.dumps({"contents": [{"parts": [{"text": "hi"}]}]}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("x-goog-api-key", key)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as ex:
            return ("FAIL", f"HTTP {ex.code} — endpoint not gemini-native")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError,
                OSError) as ex:
            return ("FAIL", f"endpoint unreachable: {getattr(ex, 'reason', ex)}")
        except Exception as ex:
            return ("FAIL", f"response parse error: {ex}")
        if "error" in body:
            return ("FAIL", f"endpoint rejected: {body['error'].get('message', body['error'])}")
        return ("PASS", "gemini generateContent ok")