import sys, os, threading, termios, io, tty, select, gc, subprocess
from .engine import Redirection
from typing import Iterable, TextIO
from abc import ABC, abstractmethod


PAGE_SIZE = 4096
CHUNK_SIZE = 1024


class CommandResult(ABC):
    _write_lock = threading.Lock()

    def __init__(self, context: Redirection, flush: bool = False):
        self.context = context
        self._write = self._write_and_flush if flush else self._write_only

    def _write_only(self, target: TextIO, data: str) -> None:
        with self._write_lock:
            target.write(data)

    def _write_and_flush(self, target: TextIO, data: str) -> None:
        with self._write_lock:
            target.write(data)
            target.flush()

    @abstractmethod
    def _consume(self) -> None:
        pass

    def output(self) -> None:
        self._consume()


class PipeCommandResult(CommandResult):
    def __init__(
        self,
        context: Redirection,
        stdout: Iterable[str] | io.TextIOWrapper = [],
        stderr: Iterable[str] | io.TextIOWrapper = [],
        process: subprocess.Popen | None = None,
        flush: bool = False,
    ) -> None:
        super().__init__(context, flush)
        self.stdout = stdout
        self.stderr = stderr
        self.process = process

    def _consume(self) -> None:
        def drain(input: Iterable[str], file: TextIO, tester: str = "") -> None:
            last_chunk = ""
            for data in input:
                if data:
                    self._write(file, data)
                    last_chunk = data
            if last_chunk and not last_chunk.endswith("\n"):
                self._write(file, "\n")

        err_thread = threading.Thread(
            target=drain, args=(self.stderr, self.context.error_file)
        )
        err_thread.start()
        drain(self.stdout, self.context.output_file)

        # 3. Cleanup
        err_thread.join()
        del err_thread
        if self.process:
            self.process.wait()
            self.stdout.close()
            self.stderr.close()


class PTYCommandResult(CommandResult):
    def __init__(
        self, context: Redirection, master_fd: int, pid: int, flush: bool = False
    ) -> None:
        super().__init__(context, flush)
        self.master_fd = master_fd
        self.pid = pid
        self._write = self._write_binary

    def _write_binary(self, target: TextIO, data: bytes) -> None:
        with self._write_lock:
            target.buffer.write(data)
            target.flush()

    # Reads Master FD and Writes to Screen Terminal
    def _consume(self) -> None:
        last_chunk = ""
        try:
            while data := os.read(self.master_fd, CHUNK_SIZE):
                self._write(self.context.output_file, data)
        except OSError:
            pass
        finally:
            if last_chunk and not last_chunk.endswith("\n"):
                self._write(self.context.output_file, "\n")
            os.close(self.master_fd)
            self.child_end.set()

    # Forwards User Keyboard Inputs To Master FD
    def _forward(self) -> None:
        # Checks if Child Process Running Command Still Exists
        read_list = [sys.stdin.fileno()]
        empty_list = []
        while not self.child_end.is_set():
            # Checks if Stdin has been written to by Keyboard
            r, _, _ = select.select(read_list, empty_list, empty_list, 0.1)
            if r:
                data = os.read(sys.stdin.fileno(), CHUNK_SIZE)
                if not data:
                    break

                # Sends Keyboard data to Master FD
                os.write(self.master_fd, data)

    def output(self) -> None:
        old_configs = termios.tcgetattr(sys.stdin.fileno())
        self.child_end = threading.Event()
        try:
            tty.setraw(sys.stdin.fileno())
            keyinput_thread = threading.Thread(target=self._forward)
            keyinput_thread.start()
            self._consume()

        finally:
            self.child_end.set()
            keyinput_thread.join()
            os.waitpid(self.pid, 0)
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_configs)
            # Garbage Collect Lists Generated from Select in Keyboard Checking Loop
            gc.collect()
            del keyinput_thread
