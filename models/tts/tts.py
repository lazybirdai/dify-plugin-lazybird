from collections.abc import Generator, Mapping
from typing import Optional

import httpx
from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

API_BASE = "https://api.lazybird.app/v2"
DEFAULT_VOICE = "tgJ2Hes6DauwTg8kFrRPLN"  # Elyssia, an official Lazybird voice
TIMEOUT = httpx.Timeout(120.0, connect=10.0)
# Sentence ends in Latin, CJK and Devanagari scripts, for splitting long text.
SENTENCE_END = r"[.!?。！？।]"
VOICE_PAGES = 10


class LazybirdError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class LazybirdText2SpeechModel(TTSModel):
    """Lazybird text to speech: one MP3 per chunk of text, streamed in order."""

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> bytes | Generator[bytes, None, None]:
        limit = self._get_model_word_limit(model, credentials) or 2000
        chunks = [c for c in self._split_text_into_sentences(content_text, limit, SENTENCE_END) if c.strip()]
        return self._stream(credentials, chunks, voice or DEFAULT_VOICE)

    def _stream(self, credentials: Mapping, chunks: list[str], voice: str) -> Generator[bytes, None, None]:
        with self._client(credentials) as client:
            for i, chunk in enumerate(chunks):
                response = client.post("/generate-speech", json={"voiceId": voice, "text": chunk.strip()})
                _raise_for_status(response)
                # Each chunk is a whole MP3 file; drop the ID3 tag of later ones so the joined stream decodes cleanly.
                yield response.content if i == 0 else _strip_id3(response.content)

    def validate_credentials(self, model: str, credentials: Mapping, user: Optional[str] = None) -> None:
        try:
            with self._client(credentials) as client:
                _raise_for_status(client.get("/me"))
        except LazybirdError as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex
        except httpx.HTTPError as ex:
            raise CredentialsValidateFailedError(f"Could not reach Lazybird: {ex}") from ex

    def get_tts_model_voices(self, model: str, credentials: dict, language: Optional[str] = None) -> Optional[list]:
        """Your own voices first, then the Lazybird library, filtered by language when one is set."""
        params = {"limit": 100}
        if language:
            # Dify sends locales such as "en-US" or "zh-Hans"; the API takes a bare language for all its accents.
            params["language"] = language.split("-")[0].lower()
        voices = []
        try:
            with self._client(credentials) as client:
                for section in ("myVoices", "library"):
                    cursor = None
                    for _ in range(VOICE_PAGES):
                        page = {**params, "section": section, **({"cursor": cursor} if cursor else {})}
                        response = client.get("/voices", params=page)
                        _raise_for_status(response)
                        data = response.json()
                        voices += [_voice_option(v) for v in data.get(section, [])]
                        cursor = data.get("nextCursor")
                        if not cursor:
                            break
        except (LazybirdError, httpx.HTTPError):
            if not voices:
                return super().get_tts_model_voices(model, credentials, None)
        return voices

    def _client(self, credentials: Mapping) -> httpx.Client:
        return httpx.Client(
            base_url=API_BASE,
            headers={"X-API-Key": credentials["api_key"], "User-Agent": "dify-plugin-lazybird"},
            timeout=TIMEOUT,
        )

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [httpx.TransportError],
            InvokeServerUnavailableError: [ServerError],
            InvokeRateLimitError: [RateLimitError],
            InvokeAuthorizationError: [AuthorizationError],
            InvokeBadRequestError: [LazybirdError],
        }


class AuthorizationError(LazybirdError):
    pass


class RateLimitError(LazybirdError):
    pass


class ServerError(LazybirdError):
    pass


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        message = response.json().get("error") or response.text
    except ValueError:
        message = response.text
    message = f"Lazybird API error {response.status_code}: {message}"
    if response.status_code == 401:
        raise AuthorizationError(response.status_code, message)
    if response.status_code == 429:
        raise RateLimitError(response.status_code, message)
    if response.status_code >= 500:
        raise ServerError(response.status_code, message)
    raise LazybirdError(response.status_code, message)


def _strip_id3(audio: bytes) -> bytes:
    if audio[:3] != b"ID3" or len(audio) < 10:
        return audio
    size = (audio[6] << 21) | (audio[7] << 14) | (audio[8] << 7) | audio[9]
    footer = 10 if audio[5] & 0x10 else 0
    return audio[10 + size + footer :]


def _voice_option(voice: dict) -> dict:
    name = voice.get("displayName") or voice["id"]
    language = voice.get("language")
    return {"name": f"{name} ({language})" if language else name, "value": voice["id"]}
