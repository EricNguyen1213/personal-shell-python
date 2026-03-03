import sys, re, io, shlex
from typing import Generator
from .redirection import Channel, Redirection


OPERATORS = {
    ">": (Channel.OUTPUT_CH, Channel.WRITE_MODE),
    "1>": (Channel.OUTPUT_CH, Channel.WRITE_MODE),
    "2>": (Channel.ERROR_CH, Channel.WRITE_MODE),
    ">>": (Channel.OUTPUT_CH, Channel.APPEND_MODE),
    "1>>": (Channel.OUTPUT_CH, Channel.APPEND_MODE),
    "2>>": (Channel.ERROR_CH, Channel.APPEND_MODE),
}

OP_PATTERN = re.compile(r"(1>>|2>>|1>|2>|>>|>)")


def operator_finder(tokenizer: shlex.shlex) -> Generator[str, None, None]:
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
