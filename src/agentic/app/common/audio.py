import asyncio
import uuid

import soundfile as sf
from cndi.annotations import Component
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage

from agentic import AgenticConfig
from agentic.app.agents import get_speech_to_text_pipeline, get_text_to_speech_pipeline


async def convert_ogg_to_mp3_async(input_path: str, output_path: str) -> None:
    process = await asyncio.create_subprocess_exec(
        # "ffmpeg", "--version",
        "ffmpeg",
        "-i",
        input_path,
        "-vn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "192k",
        "-y",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()}")


async def convert_wav_to_ogg_async(input_path: str, output_path: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-i",
        input_path,
        "-c:a",
        "libopus",
        "-b:a",
        "64k",
        "-y",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()}")


@Component
class AudioProcessor:
    def __init__(self, agentic_config: AgenticConfig):
        (
            self.tts_processor,
            self.tts_model,
            self.tts_vocoder,
            self.female_speaker_embedding,
        ) = get_text_to_speech_pipeline()
        self.asr = get_speech_to_text_pipeline()
        main_agent = agentic_config.get_agent("main")
        model_config = agentic_config.get_model(main_agent.model_id)
        self.model = init_chat_model(
            model=model_config.model,
            base_url=model_config.base_url,
            api_key=model_config.api_key
            if type(model_config.api_key) is str
            else model_config.api_key.resolve(),
        )
        self.target_words: int = 60

    async def summarize_audio_text(self, text: str) -> AIMessage:
        return await self.model.ainvoke(
            [
                {
                    "role": "user",
                    "content": (
                        f"Summarize the following text to maximum {self.target_words} words for a "
                        f"text-to-speech voice reply. Use natural spoken phrasing, no bullet points, "
                        f"no markdown, no headers — just flowing sentences a person could listen to.\n\n{text}"
                    ),
                }
            ]
        )

    async def text_to_speech(self, text: str) -> str:
        inputs = self.tts_processor(text=text, return_tensors="pt")
        speech = self.tts_model.generate_speech(
            inputs["input_ids"], self.female_speaker_embedding, vocoder=self.tts_vocoder
        )

        wav_path = f"downloads/tts_{uuid.uuid4().__str__()}.wav"
        sf.write(wav_path, speech.numpy(), samplerate=16000)

        # Telegram voice notes require .ogg/Opus — convert before sending
        ogg_path = wav_path.replace(".wav", ".ogg")
        await convert_wav_to_ogg_async(wav_path, ogg_path)
        return ogg_path

    async def speech_to_text(self, audio_path: str) -> str:
        return self.asr(audio_path)
