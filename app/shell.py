import sys, os, io, signal
from typing import Callable
from app.cmd_lib import CommandLibrary
from app.cmd_result import CommandResult
from app.utils import (
    ExitStatus,
    Redirection,
    Prompt,
    parse_tokens,
    setup_pipes,
    close_child_pipes,
)


class PersonalShell:
    def __init__(self) -> None:
        self.cmd_lib = CommandLibrary()
        self.prompter = Prompt()

    def run(self) -> None:
        while True:
            child_pids = []
            try:
                user_input = self.prompter.ask()

                # User Input Does Not Exist Case
                if not user_input:
                    continue

                # Each Pipe Section is Executed on Child Process
                pipe_sections = parse_tokens(user_input)
                stdin_pipe = None
                while section := next(pipe_sections, None):
                    cmdline, is_last = section
                    if is_last:
                        break

                    stdin_pipe, pid = self.execute_cmdline_pipe(
                        user_input, cmdline, stdin_pipe
                    )
                    child_pids.append(pid)

                # Execute Last Command Line On Parent Process
                self.execute_last_cmdline(user_input, cmdline, stdin_pipe)

            except KeyboardInterrupt:
                break

            finally:
                self.clean_cmds(child_pids)

    def execute_last_cmdline(
        self,
        user_input: str,
        cmdline: tuple[str, list[str], Redirection],
        stdin_pipe: io.TextIOWrapper | None,
    ) -> None:
        cmd, args, context = cmdline
        context.set_input(stdin_pipe)
        command_func = self.cmd_lib.find_command(context, cmd, user_input)
        self.execute(command_func, args, context.close, "master")

    def execute_cmdline_pipe(
        self,
        user_input: str,
        cmdline: tuple[str, list[str], Redirection],
        stdin_pipe: io.TextIOWrapper,
    ) -> tuple[io.TextIOWrapper, int]:

        cmd, args, context = cmdline
        stdin_pipe = setup_pipes(context, stdin_pipe)
        # Search Command Library for Correct Function To Use
        command_func = self.cmd_lib.find_command(context, cmd, user_input)
        pid = os.fork()
        if pid == 0:
            # Only Child Process Do Commands of Piped Sections
            self.execute(
                command_func, args, lambda: close_child_pipes(context, stdin_pipe)
            )
        else:
            context.close()
            return stdin_pipe, pid

    def execute(
        self,
        command_func: Callable[[list[str]], CommandResult],
        args: list[str],
        closure: Callable[[], None],
        type: str = "child",
    ) -> None:
        # Allow The Closing of Output Files Even With Crashes
        try:
            result = command_func(args)
            result.output()
        finally:
            closure()

    def clean_cmds(self, child_pids: list[int]) -> None:
        while True:
            try:
                # Waits for Any Child Process Exit, Nonblockingly
                pid, status = os.waitpid(-1, 0)
                child_pids.remove(pid)

                # Checks if the Exited Child Process is Forced
                if (
                    os.WIFEXITED(status)
                    and os.WEXITSTATUS(status) == ExitStatus.FORCEEXIT.value
                ):
                    # Kills All Child Process Safely and Parent Process
                    self.terminate_all_cmds(child_pids)

            except ChildProcessError:
                break

    def terminate_all_cmds(self, child_pids: list[int]) -> None:
        # Loops through Child PIDs and kill them safely
        for pid in child_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        sys.exit()
