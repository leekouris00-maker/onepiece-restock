"""v2.13: --pace (one check, paced like the loop) is what the cloud copy's long-running job calls."""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402


class Pace(unittest.TestCase):
    def run_main(self, argv, cfg, run_once=None):
        calls = []

        def fake(c, args, drop=None):
            calls.append((args.loop, drop))
            if run_once:
                run_once()

        with tempfile.TemporaryDirectory() as d, mock.patch.object(tb, "HERE", d), \
                mock.patch.object(tb, "load_config", return_value=cfg), \
                mock.patch.object(tb, "run_once", side_effect=fake), \
                mock.patch.object(sys, "argv", ["tcg_bot.py"] + argv):
            err = None
            try:
                tb.main()
            except RuntimeError as e:
                err = e
            path = os.path.join(d, "next_wait.txt")
            wait = int(open(path).read()) if os.path.exists(path) else None
        return calls, wait, err

    def test_one_paced_check_and_the_wait(self):
        calls, wait, _ = self.run_main(["--pace", "3"], {"pokemon": False, "auto_drop_windows": False})
        self.assertEqual(calls, [(3.0, None)])           # paced like --loop 3, no drop window on
        self.assertEqual(wait, 180)

    def test_drop_window_is_on_in_a_paced_check(self):
        now = datetime.now()
        cfg = {"pokemon": False, "auto_drop_windows": False,
               "drop_windows": [{"name": "T", "start": f"{now:%Y-%m-%d} 00:00", "end": "2099-01-01 00:00",
                                 "every_seconds": 45}]}
        calls, wait, _ = self.run_main(["--pace", "3"], cfg)
        self.assertEqual(calls[0][1]["name"], "T")
        self.assertEqual(wait, 45)

    def test_wait_is_written_even_when_the_check_fails(self):
        def boom():
            raise RuntimeError("shop exploded")
        calls, wait, err = self.run_main(["--pace", "2"], {"pokemon": False, "auto_drop_windows": False}, boom)
        self.assertIsNotNone(err)
        self.assertEqual(wait, 120)

    def test_plain_run_is_unchanged(self):
        calls, wait, _ = self.run_main([], {"pokemon": False})
        self.assertEqual(calls, [(None, None)])
        self.assertIsNone(wait)

    def test_past_windows_can_be_asked_about(self):
        # the clock passed in decides which automatic windows exist, not the real date
        cfg = {"pokemon": False, "releases": [{"name": "OP-99 Test", "date": "2031-03-07"}]}
        self.assertEqual(tb.active_window(cfg, datetime(2031, 3, 7, 9, 0))["name"], "OP-99 release day (auto)")
        self.assertIsNone(tb.active_window(cfg, datetime(2031, 3, 7, 15, 0)))


if __name__ == "__main__":
    unittest.main()
