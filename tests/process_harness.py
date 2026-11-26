"""Processos isolados para integração, sem encerrar serviços externos.

Cada instância possui somente seu Popen e seus arquivos de log. Use ``with``
mesmo durante a espera de prontidão: uma falha de startup também exige teardown.
Recrie as instâncias a cada cenário que dependa das reservas iniciais.

Procedimento: crie um diretório temporário por cenário, passe o comando do
entrypoint e ambiente explícitos e, dentro de ``with ServiceProcess(...)``,
chame ``wait_ready`` antes de enviar requests. Para restart, feche somente a
instância MCP e crie outra com a mesma chave e identidade. Logs ficam no
diretório fornecido; o harness não os despeja em erros de startup. A sondagem
de porta usa ``SO_REUSEADDR`` para não confundir conexões em ``TIME_WAIT`` da
execução anterior com um listener ativo, que continua sendo recusado.

Autoteste: ``python3 -m unittest discover -s tests -p test_process_harness.py -v``.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import time
from collections.abc import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class ServiceProcess:
    """Executa um único worker e termina exclusivamente o PID criado aqui."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        log_dir: Path,
        name: str,
        listen_address: tuple[str, int],
        env: Mapping[str, str] | None = None,
    ) -> None:
        # Recusar portas já ocupadas antes de lançar o worker evita aceitar a
        # prontidão de um serviço externo. SO_REUSEADDR evita falso negativo
        # quando a execução anterior deixou conexões em TIME_WAIT; um listener
        # ativo continua fazendo o bind falhar. Para porta 0, o subprocesso deve
        # publicar sua porta efetiva em um canal privado do próprio teste.
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(listen_address)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.stdout_path = log_dir / f"{name}.stdout"
        self.stderr_path = log_dir / f"{name}.stderr"
        self._stdout = self.stdout_path.open("wb")
        self._stderr = self.stderr_path.open("wb")
        try:
            self.process = subprocess.Popen(
                list(command),
                cwd=cwd,
                env={**os.environ, **(env or {})},
                stdin=subprocess.DEVNULL,
                stdout=self._stdout,
                stderr=self._stderr,
            )
        except BaseException:
            self._stdout.close()
            self._stderr.close()
            raise

    def wait_ready(
        self, url: str, *, status: int = 200, timeout: float = 15
    ) -> None:
        """Espera uma resposta HTTP real, sem incluir corpos/logs em erros."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Serviço terminou antes da prontidão (exit={self.process.returncode})"
                )
            try:
                with urlopen(url, timeout=min(0.5, max(0.01, deadline - time.monotonic()))) as response:
                    if response.status == status:
                        return
            except HTTPError as error:
                try:
                    if error.code == status:
                        return
                finally:
                    error.close()
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.02)
        raise TimeoutError("Serviço não ficou pronto no prazo")

    def close(self) -> None:
        """Limpeza idempotente, inclusive quando a inicialização falha."""
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self._stdout.close()
            self._stderr.close()

    def __enter__(self) -> ServiceProcess:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
