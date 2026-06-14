#!/usr/bin/env python3
"""Tests for phone_ping.py"""

import unittest
from phone_ping import ping


class TestPhonePing(unittest.TestCase):

    def test_valid_us_e164(self):
        r = ping("+14155552671")
        self.assertTrue(r["valid"])
        self.assertEqual(r["e164"], "+14155552671")
        self.assertEqual(r["region"], "US")
        self.assertEqual(r["country_code"], 1)

    def test_valid_gb_local_with_region(self):
        r = ping("+447400123456", region="GB")
        self.assertTrue(r["valid"])
        self.assertEqual(r["region"], "GB")
        self.assertIn("mobile", r["line_type"])

    def test_valid_de_number(self):
        r = ping("+49301234567")
        self.assertTrue(r["valid"])
        self.assertEqual(r["region"], "DE")

    def test_invalid_number(self):
        r = ping("+19999999999")
        self.assertFalse(r["valid"])

    def test_unparseable_returns_error(self):
        r = ping("not-a-number")
        self.assertFalse(r["valid"])
        self.assertIn("error", r)

    def test_json_fields_present(self):
        r = ping("+14155552671")
        for field in ("e164", "international", "national", "region",
                      "line_type", "timezones"):
            self.assertIn(field, r)

    def test_norwegian_number(self):
        r = ping("+4790717878")
        self.assertTrue(r["valid"])
        self.assertEqual(r["region"], "NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
