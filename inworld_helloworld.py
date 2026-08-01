import requests
import os

url = "https://api.inworld.ai/tts/v1/voice:stream"

headers = {
    "Authorization": f"Basic {os.environ['INWORLD_API_KEY']}",
    "Content-Type": "application/json"
}

payload = {
  "text": "Welcome to the Inworld TTS Playground. Type or paste your text here to hear how our advanced voice models bring your words to life.",
  "voice_id": "Sarah",
  "audio_config": {
    "audio_encoding": "MP3"
  },
  "model_id": "inworld-tts-1.5-max"
}

with requests.post(url, json=payload, headers=headers, stream=True, timeout=(5, 30)) as response:
    response.raise_for_status()
    for chunk in response.iter_lines(decode_unicode=True):
        if chunk:
            print(chunk)