"""
gemini_client.py
----------------
Wraps the Gemini Live API session.  Sends audio input and receives
both audio output and optional structured chart JSON via function calling.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")

# --------------------------------------------------------------------------- #
# System prompt template                                                        #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT_TEMPLATE = """
You are the CT Town Advisor — a knowledgeable, friendly assistant that helps
residents, developers, and officials understand Connecticut town data.

You have access to the following town documents loaded into your context:
{document_context}

When answering questions:
1. Ground every answer in the documents above.
2. If the user asks for data comparisons, trends, or statistics that can be
   visualised, ALSO call the `return_chart` function with a valid Plotly JSON
   spec in addition to your spoken answer.
3. Keep voice answers concise (2-4 sentences) — details belong in the chart.
4. If information is not in the documents, say so clearly.
"""

# --------------------------------------------------------------------------- #
# Function declaration for chart output                                         #
# --------------------------------------------------------------------------- #

CHART_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="return_chart",
            description=(
                "Return a Plotly chart specification as JSON whenever the "
                "answer involves data that benefits from visualisation."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "chart_json": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "A JSON string that is a valid Plotly figure "
                            "spec (data + layout).  Will be parsed and "
                            "rendered by the frontend."
                        ),
                    ),
                    "chart_title": types.Schema(
                        type=types.Type.STRING,
                        description="Short human-readable title for the chart.",
                    ),
                },
                required=["chart_json", "chart_title"],
            ),
        )
    ]
)


# --------------------------------------------------------------------------- #
# Live session helpers                                                          #
# --------------------------------------------------------------------------- #


def build_live_config(document_context: str) -> types.LiveConnectConfig:
    """Build the LiveConnectConfig with system prompt + chart tool."""
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        document_context=document_context
    )
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text=system_prompt)],
            role="system",
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


class CTAdvisorSession:
    """
    Manages a single Gemini Live API session.

    Usage (async context manager):
        async with CTAdvisorSession(context) as session:
            async for audio_chunk, chart_json in session.send_audio(pcm_bytes):
                ...
    """

    def __init__(self, document_context: str) -> None:
        self._context = document_context
        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        self._session = None
        self._cm = None  # the async context manager returned by connect()

    async def __aenter__(self) -> "CTAdvisorSession":
        config = build_live_config(self._context)
        self._cm = self._client.aio.live.connect(model=GEMINI_MODEL, config=config)
        self._session = await self._cm.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        if self._cm:
            await self._cm.__aexit__(*args)

    async def send_audio(
        self, pcm_bytes: bytes, sample_rate: int = 16000
    ) -> AsyncIterator[tuple[bytes | None, dict | None]]:
        """
        Send raw PCM audio to Gemini and yield (audio_chunk, None) tuples.

        - audio_chunk: raw PCM bytes from the model's spoken reply (or None)
        - chart_dict:  always None (native-audio models return audio only)
        """
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm_bytes, mime_type=f"audio/pcm;rate={sample_rate}")
        )

        async for response in self._session.receive():
            audio_chunk: bytes | None = None

            # Native-audio models return audio in server_content.model_turn.parts
            if response.server_content and response.server_content.model_turn:
                for part in response.server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        audio_chunk = part.inline_data.data

            # Also handle top-level data field (older SDK versions)
            if response.data:
                audio_chunk = response.data

            if audio_chunk:
                yield audio_chunk, None

            if response.server_content and response.server_content.turn_complete:
                break

    async def send_text(
        self, text: str
    ) -> AsyncIterator[tuple[str | None, dict | None]]:
        """
        Send a text message (for testing without a microphone).
        Yields (text_chunk, chart_dict) tuples.
        """
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=text)]),
            turn_complete=True,
        )

        async for response in self._session.receive():
            text_chunk: str | None = None
            chart_dict: dict | None = None

            if response.server_content and response.server_content.model_turn:
                for part in response.server_content.model_turn.parts:
                    if part.text:
                        text_chunk = part.text
                    if part.function_call and part.function_call.name == "return_chart":
                        args = part.function_call.args or {}
                        raw_json = args.get("chart_json", "{}")
                        try:
                            chart_dict = json.loads(raw_json)
                            chart_dict["_title"] = args.get("chart_title", "")
                        except json.JSONDecodeError:
                            chart_dict = None

            yield text_chunk, chart_dict
