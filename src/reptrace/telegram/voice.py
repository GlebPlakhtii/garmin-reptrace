"""Bounded in-memory OGG transcription; no audio or transcript logging."""

import json
import os
import urllib.request
import uuid

MAX_BYTES = 20_000_000


class VoiceError(RuntimeError):
    pass


def transcribe(audio, key=None, model=None):
    key = os.getenv("OPENAI_API_KEY", "") if key is None else key
    model = model or os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe")
    if not key:
        raise VoiceError(
            "Voice transcription is not configured. Retry after configuring the API key."
        )
    if not audio or len(audio) > MAX_BYTES or not audio.startswith(b"OggS"):
        raise VoiceError(
            "Voice audio must be an OGG note up to 20 MB. Please send it again."
        )
    boundary = "voice-" + uuid.uuid4().hex
    parts = []
    for name, value in [("model", model), ("response_format", "json")]:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.ogg"\r\nContent-Type: audio/ogg\r\n\r\n'.encode()
        + audio
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=b"".join(parts),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except (OSError, ValueError):
        raise VoiceError(
            "Transcription failed. Retry this voice note; no action was proposed or saved."
        ) from None
    transcript = result.get("text")
    if not isinstance(transcript, str) or not transcript.strip():
        raise VoiceError(
            "No speech was recognized. Retry or send a clearer voice note."
        )
    if len(transcript) > 30000:
        raise VoiceError("Transcript is too long. Please send shorter notes.")
    return transcript.strip()


def handle(bot, message, request_id):
    voice = message.get("voice", {})
    duration = voice.get("duration")
    size = voice.get("file_size")
    if (
        type(duration) not in (int, float)
        or not 0 < duration <= 300
        or (size is not None and (type(size) != int or size > MAX_BYTES or size < 1))
    ):
        raise VoiceError(
            "Voice notes must be at most five minutes and 20 MB. Send a shorter note."
        )
    if voice.get("mime_type", "audio/ogg") not in (
        "audio/ogg",
        "audio/opus",
        "application/ogg",
    ):
        raise VoiceError(
            "Unsupported voice format. Please send an OGG/Opus voice note."
        )
    key = str(message["chat"]["id"]) + ":" + str(message["message_id"])
    transcripts = bot.state.setdefault("voiceTranscripts", {})
    entry = transcripts.get(key)
    if not entry:
        audio = bot.api.download_voice(voice["file_id"])
        try:
            transcript = transcribe(audio)
        finally:
            del audio
        entry = {"text": transcript, "heard": False, "requestId": request_id}
        transcripts[key] = entry
        bot.save()
    if not entry["heard"]:
        from reptrace.telegram.bot import split_text

        for part in split_text("Heard: " + entry["text"]):
            bot.api.call(
                "sendMessage",
                {
                    "chat_id": bot.owner,
                    "text": part,
                    "reply_parameters": {"message_id": message["message_id"]},
                },
            )
        entry["heard"] = True
        bot.save()
    bot.handle_chat(
        entry["text"],
        entry.get("requestId", request_id),
        source_messages=[message],
        revision_of=bot.food_reply_target(message),
    )
