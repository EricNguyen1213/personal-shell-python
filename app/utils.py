import sys, os, shlex, io, re
import readline
from pathlib import Path
from typing import Iterator, Callable, Generator
from enum import Enum
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.completion import WordCompleter, Completion


class ExitStatus(Enum):
    FORCEEXIT = 0


class Commands(Enum):
    EXIT = "exit"
    ECHO = "echo"
    TYPE = "type"
    PWD = "pwd"
    CD = "cd"
    HISTORY = "history"
    READ_FLAG = "-r"
    WRITE_FLAG = "-w"
    APPEND_FLAG = "-a"

    @classmethod
    def get_commands(cls) -> list[str]:
        commands = {cmd.value for cmd in cls}
        for path in os.getenv("PATH", "").split(os.pathsep):
            try:
                with os.scandir(path) as entries:
                    for item in entries:
                        if item.is_file() and os.access(item.path, os.X_OK):
                            commands.add(item.name)
            except (OSError, PermissionError):
                continue
        return list(commands)


class Channel(Enum):
    OUTPUT_CH = "output_ch"
    ERROR_CH = "error_ch"
    WRITE_MODE = "w"
    APPEND_MODE = "a"


OPERATORS = {
    ">": (Channel.OUTPUT_CH, Channel.WRITE_MODE),
    "1>": (Channel.OUTPUT_CH, Channel.WRITE_MODE),
    "2>": (Channel.ERROR_CH, Channel.WRITE_MODE),
    ">>": (Channel.OUTPUT_CH, Channel.APPEND_MODE),
    "1>>": (Channel.OUTPUT_CH, Channel.APPEND_MODE),
    "2>>": (Channel.ERROR_CH, Channel.APPEND_MODE),
}

OP_PATTERN = re.compile(r"(1>>|2>>|1>|2>|>>|>)")


def operator_finder(tokenizer: shlex.shlex) -> Iterator[str]:
    for token in tokenizer:
        if ">" in token:
            parts = re.split(OP_PATTERN, token)
            yield from (p for p in parts if p)
        else:
            yield token


def parse_tokens(
    user_input: str,
) -> Generator[tuple[tuple[str, list[str], Redirection], bool], None, None]:
    input_stream = io.StringIO(user_input)
    tokenizer = shlex.shlex(input_stream, posix=True, punctuation_chars="|")
    tokenizer.whitespace_split = True
    final_tokenizer = operator_finder(tokenizer)

    is_piped = False
    cmdline, redirects, channels = [], [], {}

    while token := next(final_tokenizer, ""):
        # Define a Section of the Pipeline
        if token == "|":
            cmd, *args = cmdline
            is_piped = True
            yield ((cmd, args, Redirection(redirects, channels, is_piped)), False)
            cmdline, redirects, channels = [], [], {}
            continue

        # Determine What Channel, Output or Error, & Mode, Write or Append, is Being Adjusted
        op_configs = OPERATORS.get(token, None)
        if not op_configs:
            cmdline.append(token)
            continue

        # Grab File Name of New Redirection
        channel_name = tokenizer.get_token()
        if not channel_name:
            sys.stdout.write("parse error near `\\n'\n")
            sys.exit(0)

        # Previous Redirection Gets Logged For Continued File Creation
        if channel := channels.get(op_configs[0], None):
            redirects.append(channel[0])

        # Current Redirection Becomes Actual Output or Error File with New Mode
        channels[op_configs[0]] = (channel_name, op_configs[1])

    cmd, *args = cmdline
    yield ((cmd, args, Redirection(redirects, channels, is_piped)), True)


def setup_pipes(
    context: Redirection, prev_stdin_pipe: io.TextIOWrapper | None
) -> io.TextIOWrapper:
    # Setting stdin of Current Pipe Section
    context.set_input(prev_stdin_pipe)

    if context.output_file.isatty():
        # Current Pipe Section Outputs to stdout -> Instead Redirect its Outputs to Pipes
        piped_ends = os.pipe()
        context.set_output(os.fdopen(piped_ends[1], context.output_file.mode))

        # Retrieve stdin pipe for Next Pipe Section
        next_stdin_pipe = os.fdopen(piped_ends[0], "r")
    else:
        # Current Pipe Section Outputs to File -> Make File Readable for Next Pipe Section
        next_stdin_pipe = open(context.output_file.name, "r")
    return next_stdin_pipe


def close_child_pipes(pipe: Redirection, extra: io.TextIOWrapper) -> None:
    pipe.close()
    extra.close()
    sys.exit(0)


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


class ShellCompleter(WordCompleter):
    def get_completions(self, document, complete_event):
        # Grab Completed Objects from Original Completer
        for comp in super().get_completions(document, complete_event):
            # Return the Same Completed Value Except with Whitespace appended
            yield Completion(
                text=f"{comp.text} ",
                start_position=comp.start_position,
                display=comp.display_text,
                display_meta=comp.display_meta,
            )


class Prompt:
    def __init__(self, prompt_toolkit=False):
        if prompt_toolkit:
            self._completer_generator = self._shell_completer
            self.ask = self._tool_ask
        else:
            self._completer_generator = self._readline_completer
            self.ask = lambda: input("$ ")

        self._command_completer = self._completer_generator(Commands.get_commands())
        self._last_path = os.environ.get("PATH", "")

    # Creates a Command Completer for Prompt Toolkit
    def _shell_completer(self, cmds: list[str]) -> ShellCompleter:
        return ShellCompleter(cmds, ignore_case=True, WORD=True)

    # Creates a Command Completer for Readline Module
    def _readline_completer(self, cmds: list[str]) -> None:
        def command_completer(text, state):
            possible_commands = [cmd for cmd in cmds if cmd.startswith(text)]
            if state < len(possible_commands):
                return f"{possible_commands[state]} "
            return None

        # Parse and Bind Tab Button based on OS system, Mac or Linux
        readline.set_completer(command_completer)
        if "libedit" in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        return

    # Asks a prompt using Prompt Toolkit
    def _tool_ask(self) -> str:
        return prompt(
            "$ ",
            completer=self._command_completer,
            complete_style=CompleteStyle.MULTI_COLUMN,
        ).strip()

    # Refreshes List of Commands that exist and corresponding completer
    def check_and_refresh(self) -> None:
        current_path = os.environ.get("PATH", "")
        if self._last_path != current_path:
            self._command_completer = self._completer_generator(Commands.get_commands())
            self._last_path = current_path
