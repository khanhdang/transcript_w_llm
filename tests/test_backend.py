import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend import AudioBuffer, OllamaClient


class BackendTests(unittest.TestCase):
    def test_buffer_retains_recent_audio_and_resets(self):
        buffer = AudioBuffer(6)
        buffer.add(b"1234")
        buffer.add(b"5678")
        self.assertEqual(buffer.take(), (b"345678", True))
        self.assertEqual(buffer.take(), (b"", False))

    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            OllamaClient("https://ollama.com")

    def test_ollama_http_contract(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"models":[{"name":"local-model"}]}')

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, payload))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"message": {"content": "こんにちは"}}).encode())

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = OllamaClient("http://127.0.0.1:" + str(server.server_port))
            self.assertEqual(client.models(), ["local-model"])
            self.assertEqual(client.translate("Hello", "Japanese", "local-model"), "こんにちは")
            path, payload = requests[0]
            self.assertEqual(path, "/api/chat")
            self.assertFalse(payload["stream"])
            self.assertEqual(payload["messages"][1]["content"], "Hello")
            self.assertIn("Japanese", payload["messages"][0]["content"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_empty_translation_is_error(self):
        client = OllamaClient()
        client.request = lambda *args: {"message": {"content": " "}}
        with self.assertRaises(RuntimeError):
            client.translate("Hello", "Japanese", "test")


if __name__ == "__main__":
    unittest.main()
