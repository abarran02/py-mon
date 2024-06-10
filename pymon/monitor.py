import datetime
import subprocess
from pathlib import Path
from sys import executable

from watchdog.events import FileSystemEvent, PatternMatchingEventHandler
from watchdog.observers import Observer

from .logger import *


def check_file_excluded(check: str, exclude: str) -> bool:
    check_path = Path(check).resolve()
    exclude_path = Path(exclude).resolve()

    if exclude_path.is_dir():
        # directory is excluded
        return exclude_path in check_path.parents
    else:
        # single file is excluded
        return check_path == exclude_path

class Monitor:
    def _handle_event(self, event: FileSystemEvent):
        # 1 second cooldown to prevent watchdog event triggering double restart
        # as described in https://github.com/gorakhargosh/watchdog/issues/346
        # then check if changed file is excluded or in an excluded directory
        if (self.last_event \
            and event.src_path == self.last_event[0].src_path \
            and datetime.datetime.now() - self.last_event[1] < datetime.timedelta(seconds=1)) \
            or any([check_file_excluded(event.src_path, exc) for exc in self.exclude]):
            return

        # update most recent event with current time
        self.last_event = (
            event,
            datetime.datetime.now()
        )

        if not self.clean:
            log(Color.YELLOW, "restarting due to changes detected...")

            if self.debug:
                log(Color.CYAN, f"{event.event_type} {event.src_path}")

        self.restart_process()

    def __init__(self, arguments):
        self.filename = arguments.filename
        self.patterns = arguments.patterns
        self.args = arguments.args
        self.watch = arguments.watch
        self.debug = arguments.debug
        self.clean = arguments.clean
        self.run = arguments.run
        self.exclude = arguments.exclude

        self.process = None

        self.event_handler = PatternMatchingEventHandler(patterns=self.patterns)
        self.event_handler.on_modified = self._handle_event
        self.event_handler.on_created = self._handle_event
        self.event_handler.on_deleted = self._handle_event
        self.event_handler.on_moved = self._handle_event
        self.last_event: tuple[FileSystemEvent, datetime.datetime] = None

        self.observer = Observer()
        self.observer.schedule(self.event_handler, self.watch, recursive=True)

    def start(self):
        if not self.clean:
            log(Color.YELLOW, f"watching path: {self.watch}")
            log(Color.YELLOW, f"watching patterns: {', '.join(self.patterns)}")
            if self.exclude:
                log(Color.YELLOW, f"excluding: {', '.join(self.exclude)}")
            log(Color.YELLOW, "enter 'rs' to restart or 'stop' to terminate")

        self.observer.start()
        self.start_process()

    def stop(self):
        self.stop_process()
        self.observer.stop()
        self.observer.join()

        if not self.clean:
            log(Color.RED, "terminated process")

    def restart_process(self):
        self.stop_process()
        self.start_process()

    def start_process(self):
        if not self.clean:
            log(Color.GREEN, f"starting {self.filename}")

        if self.run:
            self.process = subprocess.Popen([self.filename, *self.args])
        else:
            self.process = subprocess.Popen([executable, self.filename, *self.args])


    def stop_process(self):
        self.process.terminate()
        self.process = None
