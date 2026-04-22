from __future__ import annotations

import argparse
import base64
import json
import queue
import threading
import time
from typing import Any, Dict, Optional

from google.cloud import dialogflow
from google.oauth2.service_account import Credentials
from mcp.server.fastmcp import FastMCP


class DialogflowStreamingSession:
    def __init__(
        self,
        keyfile_json: dict,
        language_code: str = "en-US",
        sample_rate_hertz: int = 44100,
        audio_encoding=dialogflow.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
    ):
        self.keyfile_json = keyfile_json
        self.project_id = keyfile_json["project_id"]
        self.language_code = language_code
        self.sample_rate_hertz = sample_rate_hertz
        self.audio_encoding = audio_encoding

        credentials = Credentials.from_service_account_info(self.keyfile_json)
        self.session_client = dialogflow.SessionsClient(credentials=credentials)

        self.query_input = dialogflow.QueryInput(
            audio_config=dialogflow.InputAudioConfig(
                audio_encoding=self.audio_encoding,
                language_code=self.language_code,
                sample_rate_hertz=self.sample_rate_hertz,
            )
        )

        self._audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._stop_producing = threading.Event()
        self._query_result_ready = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.session_id: Optional[int] = None
        self.last_transcript: str = ""
        self.last_intent: Optional[str] = None
        self.last_fulfillment_text: Optional[str] = None
        self.last_error: Optional[str] = None

    def _request_generator(self, session_path: str, query_params: dialogflow.QueryParameters):
        yield dialogflow.StreamingDetectIntentRequest(
            session=session_path,
            query_input=self.query_input,
            query_params=query_params,
        )

        while not self._stop_producing.is_set():
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            yield dialogflow.StreamingDetectIntentRequest(input_audio=chunk)

    def _run_stream(self, session_path: str, query_params: dialogflow.QueryParameters) -> None:
        try:
            responses = self.session_client.streaming_detect_intent(
                self._request_generator(session_path, query_params)
            )
            for response in responses:
                if response.recognition_result and response.recognition_result.transcript:
                    self.last_transcript = str(response.recognition_result.transcript)

                if response.query_result:
                    self.last_intent = (
                        response.query_result.intent.display_name
                        if response.query_result.intent
                        else None
                    )
                    self.last_fulfillment_text = str(response.query_result.fulfillment_text or "")
                    if response.query_result.query_text:
                        self.last_transcript = str(response.query_result.query_text)
                    self._query_result_ready.set()
                    break
        except Exception as exc:
            self.last_error = repr(exc)
            self._query_result_ready.set()

    def start(self, session_id: int, contexts_dict: Optional[dict] = None) -> None:
        with self._lock:
            self.stop(wait_for_result=False)
            self.last_transcript = ""
            self.last_intent = None
            self.last_fulfillment_text = None
            self.last_error = None
            self._query_result_ready.clear()
            self._stop_producing.clear()
            self.session_id = int(session_id)

            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except Exception:
                    break

            session_path = self.session_client.session_path(self.project_id, str(self.session_id))
            contexts = []
            for context_name, lifespan in (contexts_dict or {}).items():
                context_id = (
                    f"projects/{self.project_id}/agent/sessions/{self.session_id}/contexts/{context_name}"
                )
                contexts.append(dialogflow.Context(name=context_id, lifespan_count=int(lifespan)))
            query_params = dialogflow.QueryParameters(contexts=contexts)

            self._worker = threading.Thread(
                target=self._run_stream, args=(session_path, query_params), daemon=True
            )
            self._worker.start()

    def push_audio_b64(self, waveform_b64: str) -> None:
        chunk = base64.b64decode(waveform_b64.encode("ascii"), validate=True)
        try:
            self._audio_queue.put_nowait(chunk)
        except queue.Full:
            _ = self._audio_queue.get_nowait()
            self._audio_queue.put_nowait(chunk)

    def stop(self, wait_for_result: bool = True, timeout_s: float = 10.0) -> Dict[str, Any]:
        self._stop_producing.set()
        if wait_for_result:
            self._query_result_ready.wait(timeout=timeout_s)
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=0.5)
        return {
            "ok": self.last_error is None,
            "transcript": self.last_transcript or None,
            "intent": self.last_intent,
            "fulfillment_text": self.last_fulfillment_text,
            "error": self.last_error,
        }


mcp = FastMCP("Dialogflow MCP Server", json_response=True)
SESSION: Optional[DialogflowStreamingSession] = None


def _require_session() -> DialogflowStreamingSession:
    if SESSION is None:
        raise RuntimeError("Dialogflow MCP is not connected. Call connect_dialogflow first.")
    return SESSION


@mcp.tool()
def connect_dialogflow(
    keyfile_json_str: str,
    language_code: str = "en-US",
    sample_rate_hertz: int = 44100,
) -> str:
    global SESSION
    keyfile_json = json.loads(keyfile_json_str)
    SESSION = DialogflowStreamingSession(
        keyfile_json=keyfile_json,
        language_code=language_code,
        sample_rate_hertz=sample_rate_hertz,
    )
    return (
        f"Connected Dialogflow MCP for project '{SESSION.project_id}' "
        f"({language_code}, {sample_rate_hertz} Hz)."
    )


@mcp.tool()
def start_listen_dialogflow(session_id: int, contexts_json: str = "{}") -> str:
    session = _require_session()
    contexts = json.loads(contexts_json) if contexts_json else {}
    session.start(session_id=session_id, contexts_dict=contexts)
    return f"Dialogflow streaming session started (session_id={session_id})."


@mcp.tool()
def push_audio_chunk_dialogflow(waveform_b64: str) -> str:
    session = _require_session()
    session.push_audio_b64(waveform_b64)
    return "ok"


@mcp.tool()
def finish_listen_dialogflow(timeout_s: float = 10.0) -> dict:
    session = _require_session()
    return session.stop(wait_for_result=True, timeout_s=timeout_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server exposing Dialogflow streaming tools.")
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport to use (default: stdio).",
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
