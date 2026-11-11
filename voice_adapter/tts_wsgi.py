"""WSGI entry point for the YarnGPT Remi custom-TTS endpoint.

Deploy as a separate WSGI service using ``voice_adapter.tts_wsgi:application``.
Configuration is read from server environment at process startup.
"""

from .wsgi import VoiceConfig, create_app


application = create_app(VoiceConfig.from_environment())
