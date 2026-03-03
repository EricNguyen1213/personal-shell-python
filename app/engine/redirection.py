import os, sys, io
from pathlib import Path
from enum import Enum


class Channel(Enum):
    OUTPUT_CH = "output_ch"
    ERROR_CH = "error_ch"
    READ_MODE = "r"
    WRITE_MODE = "w"
    APPEND_MODE = "a"


class Redirection:
    def __init__(
        self, redirects: list[str], channels: dict[str, tuple[str, str]], is_piped: bool
    ) -> None:
        self.input_file, self.output_file, self.error_file = (
            None,
            sys.stdout,
            sys.stderr,
        )
        self._close_input = self.close_output = self.close_error = lambda: None
        self.is_piped = is_piped

        # Redirect Output
        if output_ch := channels.get(Channel.OUTPUT_CH, None):
            self.set_output(open(output_ch[0], output_ch[1].value))

        # Redirect Error
        if error_ch := channels.get(Channel.ERROR_CH, None):
            self.set_error(open(error_ch[0], error_ch[1].value))

        for fn in redirects:
            Path(fn).touch()

    # Closes All Open Files
    def close(self) -> None:
        self.close_input()
        self.close_output()
        self.close_error()

    def is_redirected(self) -> bool:
        return self.is_piped or not (
            self.output_file.isatty() and self.error_file.isatty()
        )

    def set_input(self, input_file: io.TextIOWrapper | None) -> None:
        if input_file:
            self.input_file = input_file
            self._close_input = input_file.close

    def set_output(self, file: io.TextIOWrapper):
        self.output_file = file
        self.close_output = file.close

    def set_error(self, file: io.TextIOWrapper):
        self.error_file = file
        self.close_error = file.close

    # Allows for Individual Closure of Input File While Maintaining Safety of Calling Close on All
    def close_input(self):
        self._close_input()
        self._close_input = lambda: None

    def setup_pipes(self, prev_stdin_pipe: io.TextIOWrapper | None) -> io.TextIOWrapper:
        # Setting stdin of Current Pipe Section
        self.set_input(prev_stdin_pipe)

        if self.output_file.isatty():
            # Current Pipe Section Outputs to stdout -> Instead Redirect its Outputs to Pipes
            piped_ends = os.pipe()
            self.set_output(os.fdopen(piped_ends[1], self.output_file.mode))

            # Retrieve stdin pipe for Next Pipe Section
            next_stdin_pipe = os.fdopen(piped_ends[0], "r")
        else:
            # Current Pipe Section Outputs to File -> Make File Readable for Next Pipe Section
            next_stdin_pipe = open(self.output_file.name, "r")
        return next_stdin_pipe

    def close_child_pipes(self, extra: io.TextIOWrapper) -> None:
        def closure():
            self.close()
            extra.close()
            sys.exit(0)

        return closure
