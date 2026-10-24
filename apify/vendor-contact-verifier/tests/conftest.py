"""Two local web servers stand in for the internet: `site` serves tests/fixtures, `other` is a different host (another port)
that must never receive a request. No test touches the real internet."""

import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class Hits(list):
    pass


def make_handler(root: Path, hits: Hits):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            hits.append(self.path)
            path = self.path.split("?")[0]
            target = root / path.lstrip("/")
            if target.is_dir():
                target = target / "index.html"
            redirect = Path(str(target) + ".302")
            if redirect.is_file():
                self.send_response(302)
                self.send_header("Location", redirect.read_text())
                self.end_headers()
                return
            if not target.is_file() or root not in target.resolve().parents:
                self.send_response(404)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>Not found</body></html>")
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain" if target.suffix == ".txt" else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(root: Path, hits: Hits):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, hits))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="session")
def servers(tmp_path_factory):
    work = tmp_path_factory.mktemp("web")
    site_root, other_root = work / "site", work / "other"
    shutil.copytree(FIXTURES, site_root)
    shutil.copytree(FIXTURES / "other_host", other_root)
    shutil.rmtree(site_root / "other_host")
    site_hits, other_hits = Hits(), Hits()
    other = serve(other_root, other_hits)
    other_origin = f"http://127.0.0.1:{other.server_address[1]}"
    for f in site_root.rglob("*"):  # the other host's port is only known now
        if f.is_file() and f.suffix in {".html", ".302", ".txt"}:
            f.write_text(f.read_text().replace("{{OTHER_ORIGIN}}", other_origin))
    site = serve(site_root, site_hits)
    yield {"site": f"http://127.0.0.1:{site.server_address[1]}", "other": other_origin, "site_hits": site_hits, "other_hits": other_hits}
    site.shutdown()
    other.shutdown()


@pytest.fixture()
def site(servers):
    servers["site_hits"].clear()
    servers["other_hits"].clear()
    return servers


@pytest.fixture()
def host(tmp_path):
    """Serve one fixture folder as the root of its own host (robots.txt is only honored at a host root)."""
    started = []

    def start(name: str):
        root = tmp_path / name
        shutil.copytree(FIXTURES / name, root)
        hits = Hits()
        server = serve(root, hits)
        started.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}", hits

    yield start
    for server in started:
        server.shutdown()
