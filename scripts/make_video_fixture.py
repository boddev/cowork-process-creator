"""Optional development-only video fixture using an existing encoder and Pillow.

Never bundled in Creator/output plugins. Does not install or download anything.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

from make_fixtures import write_if_new_or_same

FRAME_NAMES = (
    "01-source-inventory.png",
    "02-retained-calculations.png",
    "03-report-result.png",
)
FPS = 2
FRAMES_PER_SCREEN = 8


def run_existing_encoder(arguments: list[str], content: bytes | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, input=content, capture_output=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError("Existing developer encoder failed:\n" + result.stderr.decode("utf-8", errors="replace"))
    return result


def create_video(encoder: Path, frames: Path, output: Path) -> dict:
    from PIL import Image, ImageChops, ImageStat

    if not encoder.is_file():
        raise FileNotFoundError("Supply an already installed encoder; no installer or downloader is provided")
    if output.suffix != ".webm":
        raise ValueError("The existing VP8 encoder fixture uses a .webm output")
    output.parent.mkdir(parents=True, exist_ok=True)
    images, jpeg_frames = [], []
    for name in FRAME_NAMES:
        with Image.open(frames / name) as image:
            rgb = image.convert("RGB")
        if rgb.size != (1200, 640):
            raise ValueError("Expected the generated 1200x640 synthetic screenshot fixtures")
        images.append(rgb)
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=98, subsampling=0)
        jpeg_frames.append(buffer.getvalue())
    video_input = b"".join(frame * FRAMES_PER_SCREEN for frame in jpeg_frames)
    version = run_existing_encoder([str(encoder), "-version"]).stdout.decode("utf-8").splitlines()[0]
    with tempfile.TemporaryDirectory(prefix="n00-video-") as temporary:
        staging = Path(temporary)
        staged_video = staging / "n00-process-demo.webm"
        run_existing_encoder([
            str(encoder), "-hide_banner", "-loglevel", "error", "-n",
            "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "pipe:0",
            "-an", "-c:v", "libvpx", "-b:v", "1M", "-crf", "8",
            "-g", str(FRAMES_PER_SCREEN), "-threads", "1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact",
            str(staged_video),
        ], video_input)
        run_existing_encoder([
            str(encoder), "-hide_banner", "-loglevel", "error", "-n",
            "-i", str(staged_video), "-c:v", "png", "-f", "image2",
            str(staging / "decoded-%03d.png"),
        ])
        decoded = sorted(staging.glob("decoded-*.png"))
        expected_count = len(FRAME_NAMES) * FRAMES_PER_SCREEN
        if len(decoded) != expected_count:
            raise ValueError(f"Expected {expected_count} decoded frames, found {len(decoded)}")
        header = run_existing_encoder([
            str(encoder), "-hide_banner", "-i", str(staged_video),
            "-map", "0:v:0", "-c:v", "copy", "-an", "-f", "webm", "pipe:1",
        ]).stderr.decode("utf-8")
        duration_match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", header)
        fps_match = re.search(r"\b(\d+(?:\.\d+)?) fps\b", header)
        if duration_match is None or fps_match is None:
            raise ValueError("Existing encoder did not expose the container duration and frame rate")
        hours, minutes, seconds = duration_match.groups()
        duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if duration_seconds != expected_count / FPS or float(fps_match.group(1)) != FPS:
            raise ValueError("Encoded timestamps do not match the declared fixture timeline")
        if "1200x640" not in header or "Audio:" in header:
            raise ValueError("Encoded stream does not match the silent 1200x640 fixture contract")
        errors = []
        for index, path in enumerate(decoded):
            with Image.open(path) as decoded_image:
                actual = decoded_image.convert("RGB")
            expected_index = index // FRAMES_PER_SCREEN
            differences = [
                sum(ImageStat.Stat(ImageChops.difference(actual, expected)).mean) / 3
                for expected in images
            ]
            if min(range(len(differences)), key=differences.__getitem__) != expected_index:
                raise ValueError(f"Decoded frame {index} does not match the expected screen order")
            if differences[expected_index] > 6:
                raise ValueError(f"Decoded frame {index} exceeds the fixture fidelity threshold")
            errors.append(round(differences[expected_index], 4))
        content = staged_video.read_bytes()
        if len(content) >= 200_000_000:
            raise ValueError("Video exceeds the documented native attachment limit")
    report = {
        "fixture_kind": "synthetic-silent-screenshot-sequence-video",
        "not_a_recording_of_a_real_business_system": True,
        "format": "WebM/VP8",
        "width": 1200,
        "height": 640,
        "fps": FPS,
        "decoded_frame_count": expected_count,
        "duration_seconds": duration_seconds,
        "audio": "none",
        "timeline": [
            {"start_seconds": index * FRAMES_PER_SCREEN / FPS,
             "end_seconds_exclusive": (index + 1) * FRAMES_PER_SCREEN / FPS,
             "source_screenshot": name}
            for index, name in enumerate(FRAME_NAMES)
        ],
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "max_mean_pixel_error": max(errors),
        "developer_encoder_version": version,
        "runtime_dependency": "none; this producer and encoder are not shipped",
        "native_video_reading": "unverified",
        "limitations": [
            "Static synthetic screens with transitions, not continuous mouse or desktop activity",
            "No narration; audio understanding is not exercised",
            "Native semantic observations still require independent comparison to withheld ground truth"
        ],
    }
    write_if_new_or_same(output, content)
    write_if_new_or_same(output.with_suffix(".fixture.json"), (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    for image in images:
        image.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create_video(args.ffmpeg, args.frames, args.output), indent=2, sort_keys=True))
