#!/usr/bin/env python3
"""Watcher that restarts a child process when files change.
Usage:
  python scripts/watcher_restart.py --cmd "python main.py" --paths . core web utils config data

This script uses watchdog to watch for file changes and restarts the child process.
"""
import argparse
import subprocess
import sys
import time
import threading
import os
import signal
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import PatternMatchingEventHandler
except Exception:
    print("Missing dependency 'watchdog'. Install with: pip install watchdog")
    raise

DEFAULT_PATHS = [".", "core", "web", "utils", "config", "data"]
EXCLUDE_DIRS = {".venv", "venv", "__pycache__", ".git"}

class RestartHandler(PatternMatchingEventHandler):
    def __init__(self, on_change, patterns=None, ignore_patterns=None, ignore_directories=True, case_sensitive=False):
        super().__init__(patterns=patterns or ["*.py", "*.json", "*.json5", "*.html", "*.css", "*.js"],
                         ignore_patterns=ignore_patterns or [],
                         ignore_directories=ignore_directories,
                         case_sensitive=case_sensitive)
        self.on_change = on_change

    def on_any_event(self, event):
        # Debounce rapid events by calling the provided callback
        self.on_change(event.src_path)


class Watcher:
    def __init__(self, cmd, paths, debounce_seconds=1.5):
        self.cmd = cmd
        self.paths = [Path(p) for p in paths if Path(p).exists()]
        self.debounce_seconds = debounce_seconds
        self._restart_timer = None
        self._lock = threading.Lock()
        self.process = None
        self.observer = Observer()
        self._stopping = False

    def start_child(self):
        print(f"Starting: {self.cmd}")
        args = self.cmd if isinstance(self.cmd, list) else self.cmd.split()
        # Use sys.executable if the user passed 'python' to ensure venv python is used when venv active
        if args and args[0] == 'python':
            args[0] = sys.executable
        self.process = subprocess.Popen(args, stdout=sys.stdout, stderr=sys.stderr)

    def stop_child(self):
        if self.process and self.process.poll() is None:
            print("Stopping child process...")
            try:
                if os.name == 'nt':
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception as e:
                try:
                    self.process.terminate()
                except Exception as e2:
                    print(f"Warning: failed to terminate process gracefully: {e2}")
                print(f"Warning: error sending termination signal: {e}")
            # wait a bit for graceful shutdown
            try:
                self.process.wait(timeout=5)
            except Exception as e:
                try:
                    self.process.kill()
                except Exception as e2:
                    print(f"Warning: failed to kill process: {e2}")
                print(f"Warning: error waiting for process termination: {e}")
        self.process = None

    def restart_child(self):
        with self._lock:
            print("Restarting child due to file change...")
            self.stop_child()
            self.start_child()

    def _schedule_restart(self, _src_path=None):
        with self._lock:
            if self._restart_timer:
                self._restart_timer.cancel()
            self._restart_timer = threading.Timer(self.debounce_seconds, self.restart_child)
            self._restart_timer.daemon = True
            self._restart_timer.start()

    def _is_ignored(self, path):
        for part in Path(path).parts:
            if part in EXCLUDE_DIRS:
                return True
        return False

    def _on_change(self, src_path):
        if self._is_ignored(src_path):
            return
        print(f"Change detected: {src_path}")
        self._schedule_restart(src_path)

    def start(self):
        # Start child once
        self.start_child()
        # Setup observers
        handler = RestartHandler(on_change=self._on_change)
        for p in self.paths:
            if p.exists() and p.is_dir():
                print(f"Watching: {p}")
                self.observer.schedule(handler, str(p), recursive=True)
            elif p.exists():
                print(f"Watching file: {p}")
                self.observer.schedule(handler, str(p.parent), recursive=False)

        self.observer.start()
        try:
            while not self._stopping:
                time.sleep(1)
                # If child exited unexpectedly, restart it (useful for crashes)
                if self.process and self.process.poll() is not None:
                    rc = self.process.returncode
                    print(f"Child exited with code {rc}. Restarting...")
                    self.start_child()
        except KeyboardInterrupt:
            print("Keyboard interrupt, stopping...")
        finally:
            self.shutdown()

    def shutdown(self):
        self._stopping = True
        if self._restart_timer:
            self._restart_timer.cancel()
        try:
            self.observer.stop()
            self.observer.join(timeout=2)
        except Exception as e:
            print(f"Warning stopping observer: {e}")
        self.stop_child()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", default="python main.py", help="Command to run/restart (default: 'python main.py')")
    parser.add_argument("--paths", nargs="*", default=DEFAULT_PATHS, help="Paths to watch")
    parser.add_argument("--debounce", type=float, default=0.6, help="Debounce seconds")
    args = parser.parse_args()

    watcher = Watcher(cmd=args.cmd, paths=args.paths, debounce_seconds=args.debounce)
    try:
        watcher.start()
    except Exception as exc:
        print(f"Watcher failed: {exc}")
        watcher.shutdown()
        raise

if __name__ == '__main__':
    main()
