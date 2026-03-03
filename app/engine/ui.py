import os, readline
from typing import Callable
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.completion import WordCompleter, Completion


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
    def __init__(self, command_provider: Callable[[], list[str]], prompt_toolkit=False):
        if prompt_toolkit:
            self._completer_generator = self._shell_completer
            self.ask = self._tool_ask
        else:
            self._completer_generator = self._readline_completer
            self.ask = lambda: input("$ ")

        self._get_commands = command_provider
        self._command_completer = self._completer_generator(self._get_commands())
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
            self._command_completer = self._completer_generator(self._get_commands())
            self._last_path = current_path
