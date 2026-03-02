import sys, os, subprocess, io
from app.utils import ExitStatus, Commands, Redirection
from pathlib import Path
from typing import Callable
from app.cmd_result import CommandResult, PipeCommandResult, PTYCommandResult


DEFAULT_TERM = "xterm-256color"
TEST_NUM = 0


def find_which_path(fn: str) -> str | None:
    # Construct And Check Validity of Path to Possible File Input
    paths = os.getenv("PATH", "").split(os.pathsep)
    valid_file_path = next(
        (
            file_path
            for file_path in (Path(path) / fn for path in paths)
            if file_path.exists()
            and file_path.is_file()
            and os.access(file_path, os.X_OK)
        ),
        None,
    )
    return valid_file_path


class CommandLibrary:
    def __init__(self, history: list[str]) -> None:
        self.history = history
        self.command_lib = {
            Commands.EXIT.value: self.handle_exit,
            Commands.ECHO.value: self.handle_echo,
            Commands.TYPE.value: self.handle_type,
            Commands.PWD.value: self.handle_pwd,
            Commands.CD.value: self.handle_cd,
            Commands.HISTORY.value: self.handle_history,
        }
        self.history_flags = {
            Commands.READ_FLAG.value: self._read_history,
            Commands.WRITE_FLAG.value: self._write_history,
            Commands.APPEND_FLAG.value: self._write_history,
        }

    def find_command(
        self, context: Redirection, cmd: str
    ) -> Callable[[list[str]], CommandResult]:

        if command_func := self.command_lib.get(cmd, None):
            context.close_input()
            return lambda args: command_func(context, args)

        # Search for Custom Command Case
        if not find_which_path(cmd):
            return self.not_found(context)

        if context.is_redirected():
            return self.handle_custom_exec_pipe(context, cmd)
        return self.handle_custom_exec_pty(context, cmd)

    # Command Not Found Case
    def not_found(self, context: Redirection) -> Callable[[list[str]], CommandResult]:
        return lambda _: PipeCommandResult(
            context, stderr=[f"{self.history[-1][1]}: command not found"]
        )

    # exit Command case
    def handle_exit(self, context: Redirection, _) -> CommandResult:
        os._exit(ExitStatus.FORCEEXIT.value)
        return PipeCommandResult(context)

    # echo Command Case
    def handle_echo(self, context: Redirection, args: list[str]) -> CommandResult:
        return PipeCommandResult(context, stdout=[" ".join(args)])

    # type Command Case
    def handle_type(self, context: Redirection, args: list[str]) -> CommandResult:
        result = []
        for arg in args:
            # Argument is Actual Command
            if arg in self.command_lib:
                result.append(f"{arg} is a shell builtin\n")
                continue

            found_file_path = find_which_path(arg)
            if found_file_path:
                result.append(f"{arg} is {found_file_path}\n")
            else:
                result.append(f"{arg} not found\n")
        return PipeCommandResult(context, stdout=result)

    # pwd Command Case
    def handle_pwd(self, context: Redirection, _) -> CommandResult:
        return PipeCommandResult(context, stdout=[os.getcwd()])

    # cd Command Case
    def handle_cd(self, context: Redirection, args: list[str]) -> CommandResult:
        if len(args) > 1:
            return PipeCommandResult(context, stderr=["cd: too many arguments"])

        # Default to Home, Allow and Resolve Absolute and Relative Paths
        path_input = "~" if not args else args[0]
        cd_path = Path(path_input).expanduser().resolve()
        if cd_path.exists():
            os.chdir(cd_path)
            return PipeCommandResult(context)

        return PipeCommandResult(
            context, stderr=[f"cd: {path_input}: No such file or directory"]
        )

    def _read_history(self, file: io.TextIOWrapper) -> None:
        index = self.history[-1][0] + 1
        for line in file:
            self.history.append((index, line.strip()))
            index += 1

    def _write_history(self, file: io.TextIOWrapper) -> None:
        for line in self.history:
            file.write(f"{line[1]}\n")

    # history Command Case
    def handle_history(self, context: Redirection, args: list[str]):
        if not args:
            history_list = [f"    {i}  {cmd}\n" for i, cmd in self.history]
            return PipeCommandResult(context, stdout=history_list)

        flag, history_list, stderr = args[0], [], []
        match flag:
            case (
                Commands.READ_FLAG.value
                | Commands.WRITE_FLAG.value
                | Commands.APPEND_FLAG.value
            ):
                interact_file = self.history_flags.get(flag)
                try:
                    file_path = args[1]
                    with open(file_path, flag[1]) as f:
                        interact_file(f)
                except Exception:
                    stderr.append("history: No File Path Found")

            case str() if flag.isdigit():
                limit = int(flag)
                for i in range(len(self.history) - limit, len(self.history)):
                    index, cmdline = self.history[i]
                    history_list.append(f"    {index}  {cmdline}\n")

            case _:
                stderr.append(f"history: Invalid Input: {flag}")

        return PipeCommandResult(context, stdout=history_list, stderr=stderr)

    # Custom Or Not Found Exec Case
    def handle_custom_exec_pipe(
        self, context: Redirection, cmd: str
    ) -> Callable[[list[str]], CommandResult]:

        # global TEST_NUM
        # print(f"{TEST_NUM}: {context.input_file}")
        # TEST_NUM += 1

        # Redirection to different file case, Use different pipes for output and error stream of process
        def handler(args: list[str]) -> CommandResult:
            process = subprocess.Popen(
                [cmd, *args],
                stdin=context.input_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            return PipeCommandResult(
                context,
                stdout=process.stdout,
                stderr=process.stderr,
                process=process,
                flush=True,
            )

        return handler

    # Custom Or Not Found Exec Case
    def handle_custom_exec_pty(
        self, context: Redirection, cmd: str
    ) -> Callable[[list[str]], CommandResult]:

        # Default Sys.stdout & Sys.stderr case, Use Master/Slave Processes
        def handler(args: list[str]) -> CommandResult:
            # Generates Master/Slave Pair, redirecting child process stdin, stdout, stderr to Slave PTY
            pid, master_fd = os.forkpty()
            if pid == 0:
                try:
                    # Child Process set terminal type
                    os.environ["TERM"] = DEFAULT_TERM

                    # Child Process executes command, replacing Current Process
                    os.execvp(cmd, [cmd, *args])

                except Exception as e:
                    sys.stderr.write(f"Failed to exec: {e}\n")
                    os._exit(1)

            else:
                return PTYCommandResult(context, master_fd, pid, flush=True)

        return handler
