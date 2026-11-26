"""Verificações do harness sem dependência dos SDKs ou das portas da aplicação."""

from pathlib import Path
import sys
import tempfile
import unittest

from process_harness import ServiceProcess


HTTP_SERVER = """
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ready')

server = HTTPServer(('127.0.0.1', 0), Handler)
Path(sys.argv[1]).write_text(str(server.server_port))
server.serve_forever()
"""


class ProcessHarnessTests(unittest.TestCase):
    def test_two_independent_runs_and_owned_cleanup(self):
        import time

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(2):
                port_file = root / f"port-{index}"
                with ServiceProcess(
                    [sys.executable, "-c", HTTP_SERVER, str(port_file)],
                    cwd=root,
                    log_dir=root,
                    name=f"server-{index}",
                    listen_address=("127.0.0.1", 0),
                ) as service:
                    deadline = time.monotonic() + 15
                    while (
                        not port_file.exists()
                        and service.process.poll() is None
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    self.assertTrue(port_file.exists())
                    service.wait_ready(f"http://127.0.0.1:{port_file.read_text()}/")
                    self.assertIsNone(service.process.poll())
                self.assertIsNotNone(service.process.poll())
                service.close()

    def test_failed_startup_is_cleaned_without_dumping_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "exit=7") as caught:
                with ServiceProcess(
                    [sys.executable, "-c", "import sys; print('private'); sys.exit(7)"],
                    cwd=root,
                    log_dir=root,
                    name="failed",
                    listen_address=("127.0.0.1", 0),
                ) as service:
                    service.wait_ready("http://127.0.0.1:1/", timeout=5)
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(service.process.returncode, 7)

    def test_timeout_also_terminates_the_owned_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(TimeoutError):
                with ServiceProcess(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    cwd=root,
                    log_dir=root,
                    name="timeout",
                    listen_address=("127.0.0.1", 0),
                ) as service:
                    service.wait_ready("http://127.0.0.1:1/", timeout=0.05)
            self.assertIsNotNone(service.process.poll())

    def test_closing_one_process_does_not_terminate_another(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = [sys.executable, "-c", "import time; time.sleep(30)"]
            with ServiceProcess(
                command, cwd=root, log_dir=root, name="first",
                listen_address=("127.0.0.1", 0),
            ) as first, ServiceProcess(
                command, cwd=root, log_dir=root, name="second",
                listen_address=("127.0.0.1", 0),
            ) as second:
                first.close()
                self.assertIsNotNone(first.process.poll())
                self.assertIsNone(second.process.poll())
            self.assertIsNotNone(second.process.poll())

    def test_refuses_an_occupied_port_without_starting_a_process(self):
        import socket
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temporary, socket.socket() as external:
            root = Path(temporary)
            external.bind(("127.0.0.1", 0))
            external.listen()
            with patch("process_harness.subprocess.Popen") as spawn:
                with self.assertRaises(OSError):
                    ServiceProcess(
                        [sys.executable, "-c", "import time; time.sleep(30)"],
                        cwd=root,
                        log_dir=root,
                        name="occupied",
                        listen_address=external.getsockname(),
                    )
                spawn.assert_not_called()
            self.assertGreater(external.fileno(), -1)


if __name__ == "__main__":
    unittest.main()
