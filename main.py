import tracemalloc, os
from .app import PersonalShell


def main():
    shell = PersonalShell()
    shell.run()

    # tracemalloc.start()
    # snapshot1 = tracemalloc.take_snapshot()
    # # ... run thread-creating code ...
    # try:
    #     shell = PersonalShell()
    #     shell.run()
    # finally:
    #     snapshot2 = tracemalloc.take_snapshot()
    #     top_stats = snapshot2.compare_to(snapshot1, "lineno")
    #     for stat in top_stats[:10]:
    #         frame = stat.traceback[0]
    #         filename = os.path.basename(frame.filename)
    #         lineno = frame.lineno
    #         print(
    #             f"{filename}:{lineno}: size={stat.size_diff / 1024:.1f} KiB, count={stat.count_diff}"
    #         )


if __name__ == "__main__":
    main()
