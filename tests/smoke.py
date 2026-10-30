"""Live smoke test against the Lazybird API: `LAZYBIRD_API_KEY=... python tests/smoke.py`."""
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.entities.model import AIModelEntity  # noqa: E402
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError  # noqa: E402

from models.tts.tts import LazybirdText2SpeechModel  # noqa: E402

root = Path(__file__).resolve().parents[1]
schema = AIModelEntity(**yaml.safe_load((root / "models/tts/lazybird-tts.yaml").read_text()))
model = LazybirdText2SpeechModel(model_schemas=[schema])
creds = {"api_key": os.environ["LAZYBIRD_API_KEY"]}

model.validate_credentials("lazybird-tts", creds)
print("credentials ok")
try:
    model.validate_credentials("lazybird-tts", {"api_key": "wrong"})
    sys.exit("bad key passed")
except CredentialsValidateFailedError as ex:
    print("bad key rejected:", ex)

voices = model.get_tts_model_voices("lazybird-tts", creds, "en-US")
print(len(voices), "en voices, first:", voices[:3])
print(len(model.get_tts_model_voices("lazybird-tts", creds)), "voices without a language")

text = "Welcome back. " + "This sentence fills a long answer. " * 70
audio = b"".join(model.invoke("lazybird-tts", "t", creds, text, "tgJ2Hes6DauwTg8kFrRPLN"))
out = Path(os.environ.get("OUT", "/tmp/lazybird-dify-smoke.mp3"))
out.write_bytes(audio)
print(len(text), "chars ->", len(audio), "bytes", out)

try:
    b"".join(model.invoke("lazybird-tts", "t", creds, "Hi.", "no-such-voice"))
    sys.exit("unknown voice passed")
except InvokeError as ex:
    print("unknown voice:", type(ex).__name__, ex)
