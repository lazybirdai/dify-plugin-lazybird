import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class LazybirdProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """Check the API key against the Lazybird account it belongs to."""
        try:
            model_instance = self.get_model_instance(ModelType.TTS)
            model_instance.validate_credentials(model="lazybird-tts", credentials=credentials)
        except CredentialsValidateFailedError:
            raise
        except Exception:
            logger.exception("Lazybird credentials validation failed")
            raise
