"""Which Discord channel each kind of find goes to, and the cloud's environment-variable settings.
No network: Discord is replaced with a recorder.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import ebay_watch as ew  # noqa: E402

BOXES, SINGLES, SEALED, EBAY = ("https://discord.test/boxes", "https://discord.test/singles",
                                "https://discord.test/sealed", "https://discord.test/ebay")


def ebay_find():
    card = {"name": "Nike Air Max Plus (TN) One Piece Gomu Gomu - US 10", "max": 600, "note": "", "add_gst": True}
    item = {"itemId": "v1|555|0", "legacyItemId": "555", "title": "Nike Air Max Plus One Piece Gomu Gomu US 10",
            "price": {"value": "520.00", "currency": "AUD"}, "itemWebUrl": "https://www.ebay.com.au/itm/555",
            "itemLocation": {"country": "AU"}, "buyingOptions": ["FIXED_PRICE"]}
    return ew.make_find(card, item, ew.cost(item))


def single():
    return tb.single_find({"name": "Sabo", "num": "OP13-120", "qty": 4}, "Mayhem", 11.0,
                          "https://www.mayhemcollectables.com.au/products/sabo", "Sabo SEC")


def box():
    return {"id": "box|Gumnut|op15", "kind": "Booster box", "name": "OP-15 Booster Box", "shop": "Gumnut",
            "price": 199.0, "url": "https://www.gumnut.com.au/products/op15", "cart": "", "note": "",
            "qty": 1, "deck": "", "priority": True}


class Routing(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._send = tb.discord_send
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append(hook) or True

    def tearDown(self):
        tb.discord_send = self._send

    def hooks_for(self, alerts, finds):
        self.sent.clear()
        tb.push_discord_detailed({"alerts": alerts}, "t", "b", finds)
        return set(self.sent)

    def test_ebay_finds_get_their_own_channel(self):
        alerts = {"discord_webhook_boxes": BOXES, "discord_webhook_singles": SINGLES,
                  "discord_webhook_sealed": SEALED, "discord_webhook_ebay": EBAY}
        self.assertEqual(self.hooks_for(alerts, [ebay_find()]), {EBAY})
        self.assertEqual(self.hooks_for(alerts, [single()]), {SINGLES})
        self.assertEqual(self.hooks_for(alerts, [box()]), {BOXES})
        self.assertEqual(self.hooks_for(alerts, [ebay_find(), single(), box()]), {EBAY, SINGLES, BOXES})

    def test_without_an_ebay_webhook_they_go_to_singles_as_before(self):
        alerts = {"discord_webhook_boxes": BOXES, "discord_webhook_singles": SINGLES}
        self.assertEqual(self.hooks_for(alerts, [ebay_find()]), {SINGLES})

    def test_discord_test_message_reaches_the_ebay_channel(self):
        alerts = {"discord_webhook_boxes": BOXES, "discord_webhook_singles": SINGLES, "discord_webhook_ebay": EBAY}
        self.assertIn(EBAY, self.hooks_for(alerts, None))


class CloudSettings(unittest.TestCase):
    def test_new_webhooks_come_from_github_secrets(self):
        self.assertEqual(tb.ENV_ALERTS["DISCORD_WEBHOOK_EBAY"], "discord_webhook_ebay")
        self.assertEqual(tb.ENV_ALERTS["DISCORD_WEBHOOK_STATUS"], "discord_webhook_status")

    def test_friendly_collectibles_is_off_the_list(self):
        self.assertFalse(any("friendlycollectibles" in s["base"] for s in tb.EXTRA_SHOPIFY_SEARCH))


if __name__ == "__main__":
    unittest.main()
