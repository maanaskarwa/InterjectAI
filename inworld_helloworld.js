const options = {
  method: 'POST',
  headers: {
    'Authorization': `Basic ${process.env.INWORLD_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
  "text": "Welcome to the Inworld TTS Playground. Type or paste your text here to hear how our advanced voice models bring your words to life.",
  "voice_id": "Sarah",
  "audio_config": {
    "audio_encoding": "MP3"
  },
  "model_id": "inworld-tts-1.5-max"
}),
};

async function streamResponse() {
  try {
    const response = await fetch('https://api.inworld.ai/tts/v1/voice:stream', options);

    if (!response.ok || !response.body) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const text = decoder.decode(value, { stream: true });
      console.log(text);
    }
  } catch (err) {
    console.error(err);
  }
}

streamResponse();