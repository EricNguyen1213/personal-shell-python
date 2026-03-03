import os, readline, sys
from typing import Callable
from pathlib import Path
from abc import ABC, abstractmethod

# from prompt_toolkit import prompt
# from prompt_toolkit.shortcuts import CompleteStyle
# from prompt_toolkit.completion import WordCompleter, Completion


# class ShellCompleter(WordCompleter):
#     def get_completions(self, document, complete_event):
#         # Grab Completed Objects from Original Completer
#         for comp in super().get_completions(document, complete_event):
#             # Return the Same Completed Value Except with Whitespace appended
#             yield Completion(
#                 text=f"{comp.text} ",
#                 start_position=comp.start_position,
#                 display=comp.display_text,
#                 display_meta=comp.display_meta,
#             )


class Prompt(ABC):
    def __init__(self, command_provider: Callable[[], list[str]]):
        self._get_commands = command_provider
        self.last_path = os.environ.get("PATH", "")

    @abstractmethod
    def completer_generator(self, cmds: list[str]):
        pass

    @abstractmethod
    def ask(self) -> str:
        pass

    # Refreshes List of Commands that exist and corresponding completer
    def check_and_refresh(self) -> None:
        current_path = os.environ.get("PATH", "")
        if self.last_path != current_path:
            self.cmdline_completer = self.completer_generator(self._get_commands())
            self.last_path = current_path


# class ToolPrompt(Prompt):
#     def __init__(self, command_provider: Callable[[], list[str]]):
#         super().__init__(command_provider)
#         self.cmdline_completer = self.completer_generator(self._get_commands())

#     def completer_generator(self, cmds: list[str]) -> ShellCompleter:
#         return ShellCompleter(cmds, ignore_case=True, WORD=True)

#     def ask(self) -> str:
#         return prompt(
#             "$ ",
#             completer=self.cmdline_completer,
#             complete_style=CompleteStyle.MULTI_COLUMN,
#         ).strip()


class ReadlinePrompt(Prompt):
    def __init__(self, command_provider: Callable[[], list[str]]):
        super().__init__(command_provider)
        self.cmdline_completer = self.completer_generator(self._get_commands())

    def completer_generator(self, cmds: list[str]) -> ShellCompleter:
        def cmdline_completer(text, state):
            possibilities = []
            current_line = readline.get_line_buffer()
            before_word = current_line[: readline.get_begidx()].rstrip()

            if before_word == "" or before_word.endswith("|"):
                possibilities = [cmd for cmd in cmds if cmd.startswith(text)]
                return (
                    f"{possibilities[state]} " if state < len(possibilities) else None
                )

            path = Path(text)
            search_dir = path if path.is_dir() else path.parent
            prefix_index, prefix, name = text.rfind(os.sep), "", text
            if prefix_index >= 0:
                prefix, name = text[: prefix_index + 1], text[prefix_index + 1 :]

            for item in search_dir.iterdir():
                if not item.name.startswith(name):
                    continue
                if item.is_dir():
                    possibilities.append(f"{prefix}{item.name}/")
                elif item.is_file():
                    possibilities.append(f"{prefix}{item.name} ")

            return possibilities[state] if state < len(possibilities) else None

        return cmdline_completer

    def ask(self) -> str:
        # Parse and Bind Tab Button based on OS system, Mac or Linux
        readline.set_completer(self.cmdline_completer)
        readline.set_completer_delims(readline.get_completer_delims().replace("/", ""))
        if "libedit" in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        return input("$ ")
