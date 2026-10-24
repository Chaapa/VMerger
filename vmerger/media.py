"""FFmpeg commands are compiled from validated presets, never from model text."""

import json
import subprocess
from pathlib import Path

from .config import settings
from .contracts import StoryPlan

FORMATS = "mov,matroska,webm,avi,mp3,wav,flac,ogg,mpeg,mpegts"


def run(args: list[str], timeout: int = 900):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    if result.returncode:
        # FFmpeg diagnostics can contain paths and metadata; keep them out of API errors.
        raise ValueError(f"Media command failed ({Path(args[0]).stem}, exit {result.returncode})")
    return result.stdout


def probe(path: Path) -> dict:
    data = json.loads(
        run(
            [
                settings().ffprobe_bin,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                FORMATS,
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            30,
        )
    )
    video = next((x for x in data["streams"] if x["codec_type"] == "video"), None)
    audio = next((x for x in data["streams"] if x["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration", 0))
    if not 0 < duration <= settings().max_asset_seconds:
        raise ValueError("Source duration is outside the configured limit")
    if not video and not audio:
        raise ValueError("No supported media streams")
    if video and (video["width"] > 7680 or video["height"] > 4320):
        raise ValueError("Source resolution exceeds the processing limit")
    return {
        "duration_us": round(duration * 1_000_000),
        "width": video["width"] if video else None,
        "height": video["height"] if video else None,
        "has_audio": bool(audio),
        "kind": "video" if video else "audio",
    }


def command() -> list[str]:
    return [settings().ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "2"]


def proxy(source: Path, target: Path):
    run(
        command()
        + [
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            FORMATS,
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "scale=320:-2,fps=2",
            "-c:v",
            "libx264",
            "-b:v",
            "100k",
            "-maxrate",
            "120k",
            "-bufsize",
            "240k",
            "-c:a",
            "aac",
            "-ac",
            "1",
            "-b:a",
            "24k",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    if target.stat().st_size > 14 * 1024 * 1024:
        raise ValueError("Analysis proxy exceeds inline provider limit")


EFFECTS = {
    "none": "null",
    "warm": "colorbalance=rs=0.04:bs=-0.03",
    "monochrome": "hue=s=0",
    "fade": "fade=t=in:st=0:d=0.2",
}


def sample_frames(source: Path, duration: float, count: int):
    """Bounded JPEG samples with source timestamps; never claim audio support."""
    if not 0 < duration <= settings().max_asset_seconds or not 2 <= count <= 24:
        raise ValueError("Invalid frame sampling budget")
    for i in range(count):
        timestamp = duration * (i + 0.5) / count
        jpeg = run(command() + [
            "-protocol_whitelist", "file,pipe", "-format_whitelist", FORMATS,
            "-ss", str(timestamp), "-i", str(source), "-frames:v", "1",
            "-vf", "scale=512:512:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "5", "pipe:1",
        ], timeout=30)
        if not jpeg or len(jpeg) > 1024 * 1024:
            raise ValueError("Frame sample is missing or too large")
        yield timestamp, jpeg


def render(plan: StoryPlan, paths: dict[str, Path], assets: dict, directory: Path) -> tuple[Path, float]:
    parts = []
    for i, clip in enumerate(plan.clips):
        source = paths[str(clip.asset_id)]
        output = directory / f"part-{i:03}.mp4"
        duration = clip.end - clip.start
        args = command() + [
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            FORMATS,
            "-ss",
            str(clip.start),
            "-i",
            str(source),
        ]
        has_audio = assets[str(clip.asset_id)]["metadata"].get("has_audio", False)
        if not has_audio:
            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        args += [
            "-t",
            str(duration),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0" if has_audio else "1:a:0",
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30," + EFFECTS[clip.effect],
            "-af",
            "aresample=48000,apad",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            "48000",
            str(output),
        ]
        run(args)
        parts.append(output)
    listing = directory / "concat.txt"
    # Only generated basenames enter the concat manifest; user filenames never reach it.
    listing.write_text("\n".join(f"file '{p.name}'" for p in parts), encoding="utf-8")
    joined = directory / "joined.mp4"
    run(command() + ["-f", "concat", "-safe", "1", "-i", str(listing), "-c", "copy", str(joined)])
    output = directory / "output.mp4"
    if plan.music_asset_id:
        run(
            command()
            + [
                "-i",
                str(joined),
                "-stream_loop",
                "-1",
                "-i",
                str(paths[str(plan.music_asset_id)]),
                "-filter_complex",
                f"[1:a]volume={plan.music_gain}[music];"
                "[0:a][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
                "-map",
                "0:v:0",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    else:
        run(command() + ["-i", str(joined), "-c", "copy", "-movflags", "+faststart", str(output)])
    # Complete decode catches corruption beyond the header. Publication follows this check.
    run(command() + ["-xerror", "-i", str(output), "-f", "null", "-"])
    info = probe(output)
    expected = sum(c.end - c.start for c in plan.clips)
    actual = info["duration_us"] / 1_000_000
    if abs(actual - expected) > max(0.25, len(plan.clips) / 30 + 0.1):
        raise ValueError("Rendered duration differs from validated plan")
    return output, actual
