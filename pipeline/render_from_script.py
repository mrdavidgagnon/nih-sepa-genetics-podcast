"""Render a checked-in Host/Rowan Markdown script without publishing anything."""
import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
import edge_tts
import imageio_ffmpeg

VOICE = {"host": "en-US-AvaMultilingualNeural", "rowan": "en-GB-SoniaNeural"}
RATE = {"host": "-3%", "rowan": "-2%"}


def spoken_text(text: str) -> str:
    """Remove Markdown-only emphasis delimiters before sending text to TTS."""
    return text.replace("*", "").replace("`", "")


def parse_script(path: Path):
    turns = []
    for line in path.read_text().splitlines():
        match = re.match(r"^\*\*(Host|Rowan|Turing):\*\*\s+(.+)$", line)
        if match:
            role = match.group(1).lower().replace("turing", "rowan")
            turns.append((role, match.group(2).strip()))
    if not turns:
        raise ValueError(f"No Host/Rowan turns found in {path}")
    return turns


async def synthesize(path: Path, role: str, text: str):
    for attempt in range(4):
        try:
            await edge_tts.Communicate(spoken_text(text), VOICE[role], rate=RATE[role]).save(str(path))
            return
        except Exception:
            if attempt == 3:
                raise
            await asyncio.sleep(2 + attempt)


async def render(script: Path, output: Path):
    script = script.resolve()
    output = output.resolve()
    turns = parse_script(script)
    parts = output.parent / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    files = []
    for index, (role, text) in enumerate(turns):
        part = parts / f"{index:03d}-{role}.mp3"
        await synthesize(part, role, text)
        files.append(part)
    concat = output.parent / "concat.txt"
    concat.write_text("".join(f"file '{part.resolve().as_posix()}'\n" for part in files))
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat), "-c:a", "libmp3lame", "-b:a", "128k", str(output),
    ], check=True)
    print(f"rendered {output} from {len(turns)} turns")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    asyncio.run(render(args.script, args.output))
