"""Exercise the actual decoder used by microphone transcription."""
import io
import unittest
import wave

import numpy as np
from faster_whisper.audio import decode_audio


class AudioTests(unittest.TestCase):
    def test_microphone_wav_decodes_and_resamples(self):
        rate = 48000
        samples = (np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 16000).astype("<i2")
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(samples.tobytes())
        audio.seek(0)
        decoded = decode_audio(audio, sampling_rate=16000)
        self.assertEqual(decoded.shape, (16000,))
        self.assertEqual(decoded.dtype, np.float32)
        self.assertTrue(np.isfinite(decoded).all())
        self.assertGreater(float(np.max(np.abs(decoded))), 0.4)
        self.assertLess(float(np.max(np.abs(decoded))), 0.6)


if __name__ == "__main__":
    unittest.main()
