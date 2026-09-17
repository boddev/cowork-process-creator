"""Developer-only editor of existing window recordings; never generates application UI."""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_plan(plan):
    if plan.get("schema_version") != 1 or plan.get("fps") != 10:
        raise ValueError("Expected this pilot's v1, 10 fps edit plan")
    if not plan.get("clips"):
        raise ValueError("No recorded intervals supplied")
    last_end = {}
    for source in plan["sources"].values():
        if (Path(source["file"]).name != source["file"]
                or "/" in source["file"] or "\\" in source["file"]):
            raise ValueError("Raw input names must be basenames, not private paths")
    for clip in plan["clips"]:
        source = plan["sources"][clip["source"]]
        start, end = clip["start"], clip["end"]
        if (not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start < end or start < last_end.get(clip["source"], 0)):
            raise ValueError("Source intervals must be positive and chronological")
        x, y, width, height = clip["crop"]
        sw, sh = source["dimensions"]
        if not (0 <= x < sw and 0 <= y < sh and width > 0 and height > 0
                and x + width <= sw and y + height <= sh):
            raise ValueError("Crop exceeds the actual recorded window")
        if clip["source"] == "excel" and x + width > 2780:
            raise ValueError("Excel crop would expose the account/profile area")
        if not 1 <= clip["chapter"] <= 8:
            raise ValueError("Unexpected chapter")
        last_end[clip["source"]] = end


def timecode(seconds):
    milliseconds = round(seconds * 1000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def text_block(draw, text, xy, font, width, color, line_height):
    x, y = xy
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and draw.textlength(candidate, font=font) > width:
                draw.text((x, y), line, font=font, fill=color)
                y += line_height
                line = word
            else:
                line = candidate
        draw.text((x, y), line, font=font, fill=color)
        y += line_height
    return y


def caption_frame(clip, source, position, count):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1920, 1080), "#0c1727")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype("arialbd.ttf", 37)
    heading = ImageFont.truetype("arialbd.ttf", 40)
    body = ImageFont.truetype("arial.ttf", 27)
    small = ImageFont.truetype("arial.ttf", 21)
    label = ImageFont.truetype("arialbd.ttf", 21)
    draw.text((24, 16), "SEC filing to Excel", font=title, fill="#ffffff")
    draw.text((1440, 25), "FINANCIAL SERVICES / KO", font=label, fill="#70e2c3")
    draw.line((24, 68, 1896, 68), fill="#29405b", width=2)
    draw.rectangle((24, 82, 1420, 1046), fill="#182638")
    x = 1452
    draw.text((x, 102), f"STEP {clip['chapter']} OF 8", font=label, fill="#70e2c3")
    y = text_block(draw, clip["title"], (x, 150), heading, 430, "#ffffff", 47)
    y = text_block(draw, clip["action"], (x, y + 28), body, 430, "#eef4ff", 35)
    draw.line((x, y + 29, 1880, y + 29), fill="#29405b", width=2)
    y += 58
    draw.text((x, y), "WORK TO AUTOMATE", font=label, fill="#70e2c3")
    y = text_block(draw, clip["target"], (x, y + 36), body, 430, "#eef4ff", 35)
    y = text_block(draw, clip["detail"], (x, y + 30), small, 430, "#b5c5d9", 29)
    if y > 970:
        raise ValueError(f"Caption overflows the frame: {clip['action']}")
    draw.text((x, 982), f"TAKE {source['take']} | CUT {position}/{count} | 1x", font=label, fill="#70e2c3")
    draw.text((24, 1053), "ACTUAL APPLICATION CAPTURE | AGENT-OPERATED | EDITED | NO NATIVE COWORK INVOCATION", font=small, fill="#b5c5d9")
    return image


def render(plan, raw_dir, encoder, destination):
    from PIL import Image

    fps = plan["fps"]
    timeline = []
    total_frames = 0
    encode_command = [
        str(encoder), "-hide_banner", "-loglevel", "error", "-f", "image2pipe",
        "-c:v", "mjpeg", "-framerate", str(fps), "-i", "pipe:0", "-an",
        "-c:v", "libvpx", "-deadline", "good", "-cpu-used", "4", "-threads", "2",
        "-b:v", "2400k", "-crf", "10", "-g", "100", "-pix_fmt", "yuv420p",
        "-map_metadata", "-1", "-n", str(destination / "workflow.webm"),
    ]
    with tempfile.TemporaryFile() as encode_log:
        process = subprocess.Popen(encode_command, stdin=subprocess.PIPE, stderr=encode_log)
        try:
            for index, clip in enumerate(plan["clips"], 1):
                source = plan["sources"][clip["source"]]
                x, y, width, height = clip["crop"]
                ratio = min(1396 / width, 964 / height)
                out_width = int(width * ratio) // 2 * 2
                out_height = int(height * ratio) // 2 * 2
                left = 24 + (1396 - out_width) // 2
                top = 82 + (964 - out_height) // 2
                base = caption_frame(clip, source, index, len(plan["clips"]))
                frame_dir = destination / f"cut-{index:02}"
                frame_dir.mkdir()
                command = [
                    str(encoder), "-hide_banner", "-loglevel", "error",
                    "-ss", str(clip["start"]), "-i", str(raw_dir / source["file"]),
                    "-t", str(clip["end"] - clip["start"]), "-an",
                    "-vf", f"crop={width}:{height}:{x}:{y},scale={out_width}:{out_height}",
                    "-r", str(fps), "-c:v", "png", "-pix_fmt", "rgb24",
                    "-n", str(frame_dir / "%05d.png"),
                ]
                frames = 0
                decoded = subprocess.run(command, capture_output=True, timeout=180)
                if decoded.returncode:
                    raise RuntimeError(decoded.stderr.decode(errors="replace"))
                for path in sorted(frame_dir.glob("*.png")):
                    with Image.open(path) as pixels:
                        image = base.copy()
                        image.paste(pixels, (left, top))
                    if index == len(plan["clips"]) and frames == 50:
                        image.save(destination / "poster.jpg", quality=95)
                    with io.BytesIO() as jpeg:
                        image.save(jpeg, format="JPEG", quality=95, subsampling=0)
                        process.stdin.write(jpeg.getvalue())
                    image.close()
                    path.unlink()
                    frames += 1
                frame_dir.rmdir()
                base.close()
                if frames < fps * 3:
                    raise ValueError(f"Clip contains insufficient recorded footage: {index}")
                start = total_frames / fps
                total_frames += frames
                timeline.append({
                    **clip, "take": source["take"], "output_start": start,
                    "output_end": total_frames / fps, "decoded_frames": frames,
                    "display_rectangle": [left, top, out_width, out_height],
                })
                print(f"Clip {index}/{len(plan['clips'])}: {frames} actual decoded frames", flush=True)
            process.stdin.close()
            result = process.wait(timeout=180)
            if result:
                encode_log.seek(0)
                raise RuntimeError(encode_log.read().decode(errors="replace"))
        finally:
            if not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if not (destination / "poster.jpg").is_file():
        raise ValueError("Final recorded save interval did not produce a poster")
    return timeline, total_frames


def write_evidence(plan, timeline, frames, encoder, destination):
    chapters = []
    for clip in timeline:
        if not chapters or chapters[-1]["chapter"] != clip["chapter"]:
            chapters.append({
                "chapter": clip["chapter"], "title": clip["title"],
                "start": clip["output_start"], "end": clip["output_end"],
            })
        else:
            chapters[-1]["end"] = clip["output_end"]
    evidence = {
        "schema_version": 1,
        "kind": "edited-real-application-recording",
        "actor": "agent-operated browser and desktop UI",
        "capture_date": "2026-09-16",
        "capture": {
            "method": "Browser getDisplayMedia window selection and MediaRecorder",
            "permission": "Explicit native window-picker consent",
            "audio": False, "uploads": False, "raw_storage": "private, outside repository",
        },
        "sources": plan["sources"], "disclosures": plan["disclosures"],
        "output": {
            "file": "workflow.webm", "codec": "VP8", "container": "WebM",
            "dimensions": [1920, 1080], "fps": plan["fps"], "frames": frames,
            "duration_seconds": frames / plan["fps"], "audio": False,
            "bytes": (destination / "workflow.webm").stat().st_size,
            "sha256": digest(destination / "workflow.webm"),
        },
        "editing": {
            "recipe": "../edit.json", "recipe_sha256": digest(HERE / "edit.json"),
            "script": "../assemble_recording.py", "script_sha256": digest(Path(__file__)),
            "encoder": encoder.name, "encoder_sha256": digest(encoder),
            "time_mapping": "Requested source intervals passed to FFmpeg; output times use actual decoded frame counts at 10 fps. Boundary rounding follows CFR resampling.",
            "application_pixels": "Decoded recorded pixels, cropped and scaled only; captions occupy a separate surrounding panel.",
            "speed_changes": False, "generated_application_frames": False,
        },
        "chapters": chapters, "timeline": timeline,
        "native_cowork": {
            "creation": "not-attempted", "install": "not-attempted",
            "invocation": "not-attempted", "evaluation": "not-attempted",
        },
    }
    (destination / "recording-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    captions = "WEBVTT\n\n"
    for clip in timeline:
        captions += f"{timecode(clip['output_start'])} --> {timecode(clip['output_end'])}\n{clip['title']}: {clip['action']}\n{clip['target']}\n\n"
    (destination / "captions.vtt").write_text(captions, encoding="utf-8")
    chapter_text = "WEBVTT\n\n"
    for chapter in chapters:
        chapter_text += f"{timecode(chapter['start'])} --> {timecode(chapter['end'])}\n{chapter['title']}\n\n"
    (destination / "chapters.vtt").write_text(chapter_text, encoding="utf-8")
    (destination / "viewer-data.js").write_text(
        "const recordingEvidence = " + json.dumps(evidence) + ";\n", encoding="utf-8"
    )
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--replace-generated", action="store_true")
    args = parser.parse_args()
    plan = json.loads((HERE / "edit.json").read_text(encoding="utf-8"))
    check_plan(plan)
    for source in plan["sources"].values():
        path = args.raw_dir / source["file"]
        if digest(path) != source["sha256"]:
            raise ValueError(f"Raw capture fingerprint mismatch: {source['file']}")
    output = HERE / "demo"
    names = ("workflow.webm", "poster.jpg", "recording-evidence.json", "captions.vtt", "chapters.vtt", "viewer-data.js")
    if not args.replace_generated and any((output / name).exists() for name in names):
        raise FileExistsError("Existing recording delivery; use --replace-generated deliberately")
    with tempfile.TemporaryDirectory(prefix="edited-recording-", dir=args.raw_dir) as temp:
        destination = Path(temp)
        timeline, frames = render(plan, args.raw_dir, args.ffmpeg, destination)
        evidence = write_evidence(plan, timeline, frames, args.ffmpeg, destination)
        output.mkdir(exist_ok=True)
        for name in names:
            (destination / name).replace(output / name)
    print(json.dumps(evidence["output"], indent=2))


if __name__ == "__main__":
    main()
