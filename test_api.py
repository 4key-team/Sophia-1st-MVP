"""Simple manual harness for exercising core REST endpoints against a running backend."""

from fastapi.testclient import TestClient

from main import app

API_URL = "http://127.0.0.1:8000"
CLIENT = TestClient(app)
API_KEY = "dev-key"  # Replace with your actual API key
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
TEST_FILE = "full_test_output.wav"


def test_transcribe():
    with open(TEST_FILE, "rb") as f:
        files = {"file": (TEST_FILE, f, "audio/wav")}
        response = CLIENT.post("/transcribe", files=files, headers=HEADERS)
    print("Transcribe Response:", response.status_code, response.json())


def test_generate_response():
    data = {"text": "Hello Sophia, how are you?"}
    response = CLIENT.post("/generate-response", json=data, headers=HEADERS)
    print("Generate Response:", response.status_code, response.json())


def test_synthesize():
    data = {"text": "Hello! This is Sophia speaking."}
    response = CLIENT.post("/synthesize", json=data, headers=HEADERS)
    print("Synthesize Response:", response.status_code, response.json())


def test_chat():
    with open(TEST_FILE, "rb") as f:
        files = {"file": (TEST_FILE, f, "audio/wav")}
        response = CLIENT.post("/chat", files=files, headers=HEADERS)
    print("Chat Response:", response.status_code, response.json())


if __name__ == "__main__":
    test_transcribe()
    test_generate_response()
    test_synthesize()
    test_chat()
