"""Protect local work and fork identity using disposable Git repositories, offline."""
import subprocess
import os
import signal
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_api  # establishes isolated app data before any app import
from app import restart, updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="music-generator-git-")
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(updater, "ROOT", self.root)
        self.root_patch.start()
        # These tests isolate repository operations; concurrent API work is covered separately.
        self.busy_patch = patch.object(updater.db, "one", return_value={"n": 0})
        self.busy_patch.start()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Offline test")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.root / "disabled-hooks"))
        (self.root / "song-app.txt").write_text("base")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD")
        (self.root / "song-app.txt").write_text("remote update")
        self.commit("remote update")
        self.remote = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.remote)
        self.git("reset", "--hard", self.base)
        self.git("remote", "add", "origin", updater.REPO_URL)
        self.real_git = updater.git
        self.calls = []

        def offline_git(*args, **kwargs):
            self.calls.append(args)
            # The fixture supplies origin/main directly. Never contact GitHub in tests.
            if args[0] == "fetch":
                return ""
            return self.real_git(*args, **kwargs)

        self.offline = patch.object(updater, "git", side_effect=offline_git)
        self.offline.start()

    def tearDown(self):
        self.offline.stop()
        self.busy_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, title):
        self.git("add", "--all")
        self.git("commit", "-q", "-m", title)

    def assert_not_merged(self):
        self.assertFalse(any(args[0] in {"merge", "pull", "checkout"} for args in self.calls), self.calls)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_clean_main_fast_forwards_to_checked_fork(self):
        status = updater._status()
        self.assertEqual((status["behind"], status["ahead"], status["dirty"]), (1, 0, False))
        result = updater._apply()
        self.assertTrue(self.remote.startswith(result["current"]))
        self.assertEqual((self.root / "song-app.txt").read_text(), "remote update")
        self.assertTrue(any(args[:2] == ("merge", "--ff-only") for args in self.calls))

    def test_wrong_origin_refused_before_fetch(self):
        self.git("remote", "set-url", "origin", "https://github.com/rabbitfiremediacreation/music-generator.git")
        with self.assertRaisesRegex(RuntimeError, "abartiggut"):
            updater._apply()
        self.assertFalse(any(args[0] == "fetch" for args in self.calls))
        self.assert_not_merged()

    def test_development_branch_refused(self):
        self.git("switch", "-c", "my-development")
        with self.assertRaisesRegex(RuntimeError, "main"):
            updater._apply()
        self.assert_not_merged()

    def test_tracked_changes_are_preserved(self):
        (self.root / "song-app.txt").write_text("my edit")
        with self.assertRaises(RuntimeError):
            updater._apply()
        self.assert_not_merged()
        self.assertEqual((self.root / "song-app.txt").read_text(), "my edit")

    def test_untracked_changes_are_preserved(self):
        (self.root / "my-new-feature.py").write_text("personal work")
        with self.assertRaises(RuntimeError):
            updater._apply()
        self.assert_not_merged()
        self.assertEqual((self.root / "my-new-feature.py").read_text(), "personal work")

    def test_local_commits_are_preserved(self):
        (self.root / "local-feature.txt").write_text("local feature")
        self.commit("local feature")
        local_head = self.git("rev-parse", "HEAD")
        with self.assertRaises(RuntimeError):
            updater._apply()
        self.assertEqual(self.git("rev-parse", "HEAD"), local_head)
        self.assertFalse(any(args[0] in {"merge", "pull"} for args in self.calls))

    def test_edit_during_check_is_preserved(self):
        status = updater._status()
        (self.root / "edited-after-check.txt").write_text("racing edit")
        with patch.object(updater, "_status", return_value=status):
            with self.assertRaises(RuntimeError):
                updater._apply()
        self.assert_not_merged()

    def test_rechecks_active_work_before_git_merge(self):
        for jobs, analyses in ((1, 0), (0, 1)):
            with self.subTest(jobs=jobs, analyses=analyses):
                self.calls.clear()
                with patch.object(updater.db, "one", return_value={"n": jobs}), \
                        patch.object(updater.lifecycle, "analyses", analyses):
                    with self.assertRaises(RuntimeError):
                        updater._apply()
                self.assert_not_merged()

    def test_zip_install_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="music-generator-zip-") as folder:
            root = Path(folder)
            marker = root / "user.txt"
            marker.write_text("preserve me")
            with patch.object(updater, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "ZIP"):
                    updater._status()
                with self.assertRaisesRegex(RuntimeError, "ZIP"):
                    updater._apply_nogit({})
            self.assertEqual(marker.read_text(), "preserve me")
            self.assertFalse((root / ".git").exists())

    def test_mac_restart_spawns_python_helper_and_signals_only_itself(self):
        own_pid = os.getpid()
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "platform", "darwin"), \
                patch.object(updater.db, "DATA", self.root), \
                patch.object(updater.subprocess, "Popen") as spawn, \
                patch.object(updater.os, "kill") as kill:
            updater._restart(18765)
            command = spawn.call_args.args[0]
            self.assertEqual(command, [sys.executable, "-m", "app.restart", "--parent-pid", str(own_pid),
                                       "--port", "18765"])
            self.assertTrue(spawn.call_args.kwargs["start_new_session"])
            self.assertNotIn("shell", spawn.call_args.kwargs)
            kill.assert_called_once_with(own_pid, signal.SIGTERM)

    def test_mac_helper_waits_for_parent_and_port_without_signalling_any_pid(self):
        with patch.object(sys, "platform", "darwin"), \
                patch.object(restart.os, "getppid", side_effect=[71234, 71234, 1, 1]), \
                patch.object(restart, "port_open", side_effect=[True, False]), \
                patch.object(restart.time, "monotonic", side_effect=[0, 1, 2, 3]), \
                patch.object(restart.time, "sleep") as sleep, \
                patch.object(restart.subprocess, "Popen") as spawn, \
                patch.object(restart.os, "kill") as kill:
            self.assertEqual(restart.main(["--parent-pid", "71234", "--port", "18765"]), 0)
            self.assertEqual(sleep.call_count, 3)
            self.assertEqual(spawn.call_args.args[0], [sys.executable, "-m", "uvicorn", "app.main:app",
                                                      "--host", "127.0.0.1", "--port", "18765"])
            self.assertNotIn("shell", spawn.call_args.kwargs)
            kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
