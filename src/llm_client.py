"""
llm_client.py
-------------
Thin, provider-agnostic OpenAI-compatible chat-completion client.

Features:
- Exponential back-off with full jitter on 429 / 5xx responses
- Respects ``Retry-After`` response headers
- Configurable per-request and per-instance timeouts
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

import requests


class OpenAICompatClient:
    """
    Minimal HTTP client for any OpenAI-compatible ``/v1/chat/completions``
    endpoint (DeepSeek, Groq, OpenAI, etc.).

    Args:
        base_url: API root URL (trailing slash is stripped automatically).
        api_key: Bearer token for the ``Authorization`` header.
        model: Model identifier string passed in each request payload.
        timeout: Per-request HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _retry_after_seconds(self, response: requests.Response) -> Optional[float]:
        """Parse the ``Retry-After`` header if present."""
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _jittered_delay(self, attempt: int, base: float = 1.2, cap: float = 30.0) -> float:
        """Full-jitter exponential back-off delay in seconds."""
        ceiling = min(cap, base * (2 ** attempt))
        return ceiling * (0.75 + random.random() * 0.5)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 1200,
        max_retries: int = 8,
    ) -> str:
        """
        Send a chat-completion request and return the assistant's reply text.

        Args:
            messages: Conversation history in OpenAI message format.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens to generate.
            max_retries: Number of retry attempts on transient errors.

        Returns:
            The content string of the first completion choice.

        Raises:
            requests.HTTPError: When all retries are exhausted.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )

                # Transient server errors → back off and retry
                if response.status_code in (429, 500, 502, 503, 504):
                    retry_hint = self._retry_after_seconds(response)
                    delay = (
                        min(30.0, retry_hint) * (0.75 + random.random() * 0.5)
                        if retry_hint is not None
                        else self._jittered_delay(attempt)
                    )
                    last_error = requests.HTTPError(
                        f"HTTP {response.status_code}", response=response
                    )
                    if attempt < max_retries:
                        time.sleep(delay)
                    continue

                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

            except (
                requests.Timeout,
                requests.ConnectionError,
                requests.HTTPError,
            ) as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(self._jittered_delay(attempt))

        raise last_error  # type: ignore[misc]
