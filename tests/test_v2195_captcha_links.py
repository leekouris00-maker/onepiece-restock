"""v2.19.5: CAPTCHA notices link each shop's name to its front page."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import captcha_watch as cw  # noqa: E402


class CaptchaLinks(unittest.TestCase):
    E = {"kind": "Cloudflare challenge", "status": 429}

    def test_link(self):
        self.assertEqual(cw.shop_link("Kollecter", "kollecter.com.au"), "[Kollecter](https://kollecter.com.au/)")

    def test_escapes_markdown(self):
        self.assertEqual(cw.shop_link("A [B] (C)", "x.com"), r"[A \[B\] \(C\)](https://x.com/)")

    def test_no_host(self):
        self.assertEqual(cw.shop_link("Shop", ""), "Shop")

    def test_cloud_single(self):
        m = cw.message("Kollecter", "kollecter.com.au", self.E, how=cw.HOW_DISCORD, cloud=True)
        self.assertIn("**[Kollecter](https://kollecter.com.au/) is asking", m)

    def test_pc_single_429_and_other(self):
        self.assertIn("(https://a.com/)", cw.message("A", "a.com", self.E))
        self.assertIn("(https://a.com/)", cw.message("A", "a.com", {"kind": "hCaptcha", "status": 403}))

    def test_digest(self):
        items = [("Pocket Games", "pocketgames.com.au", self.E), ("Rogue Online", "rogueonline.com.au", self.E)]
        for cloud in (True, False):
            d = cw.digest(items, cloud=cloud)
            self.assertIn("• **[Pocket Games](https://pocketgames.com.au/)**", d)
            self.assertIn("• **[Rogue Online](https://rogueonline.com.au/)**", d)


if __name__ == "__main__":
    unittest.main()
