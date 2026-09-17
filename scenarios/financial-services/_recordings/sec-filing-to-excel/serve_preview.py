"""Loopback-only public pilot preview with byte ranges for video chapter seeking."""

import argparse
from email.utils import formatdate
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


HERE = Path(__file__).resolve().parent
PUBLIC_PATHS = {
    "/", "/index.html", "/initial.xlsx", "/completed.xlsx", "/HOW_TO.md",
    "/source.json", "/pilot.json", "/workbook-evidence.json",
    "/demo/workflow.webm", "/demo/poster.jpg", "/demo/recording-evidence.json",
    "/demo/captions.vtt", "/demo/chapters.vtt", "/demo/viewer-data.js",
}


def byte_range(header, size):
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or size <= 0:
        raise ValueError("Unsupported or unsatisfiable byte range")
    first, last = match.groups()
    if not first:
        if not last or int(last) <= 0:
            raise ValueError("Invalid suffix range")
        return max(0, size - int(last)), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start > end or start >= size:
        raise ValueError("Unsatisfiable byte range")
    return start, end


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404, "Public index is unavailable")
        return None

    def send_head(self):
        self.remaining = None
        if unquote(urlsplit(self.path).path) not in PUBLIC_PATHS:
            self.send_error(404, "Not a public pilot asset")
            return None
        path = Path(self.translate_path(self.path))
        if not path.resolve().is_relative_to(HERE):
            self.send_error(404, "Not a public pilot asset")
            return None
        requested = self.headers.get("Range")
        if not requested or not path.is_file():
            return super().send_head()
        stream = path.open("rb")
        stat = os.fstat(stream.fileno())
        modified = formatdate(stat.st_mtime, usegmt=True)
        if self.headers.get("If-Range", modified) != modified:
            stream.close()
            return super().send_head()
        try:
            start, end = byte_range(requested, stat.st_size)
        except ValueError:
            stream.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{stat.st_size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.remaining = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(self.remaining))
        self.send_header("Content-Range", f"bytes {start}-{end}/{stat.st_size}")
        self.send_header("Last-Modified", modified)
        self.end_headers()
        stream.seek(start)
        return stream

    def copyfile(self, source, output):
        if self.remaining is None:
            return super().copyfile(source, output)
        while self.remaining:
            block = source.read(min(65536, self.remaining))
            if not block:
                raise OSError("Public asset was truncated during a range response")
            output.write(block)
            self.remaining -= len(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler) as server:
        print(f"Public pilot preview: http://127.0.0.1:{args.port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
