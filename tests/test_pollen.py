"""Tests for pollen-state semantics."""

import unittest

from custom_components.klimat_domowy.pollen import (
    is_high,
    is_known,
    is_low,
    is_none_detected,
    is_present,
)


class PollenStateTests(unittest.TestCase):
    def test_source_brak_means_no_pollen_detected(self):
        self.assertTrue(is_known("brak"))
        self.assertTrue(is_none_detected("brak"))
        self.assertFalse(is_high("brak"))
        self.assertFalse(is_present("brak"))

    def test_unavailable_values_are_missing_data(self):
        for value in (None, "", "unknown", "unavailable", "n/a", "no data"):
            with self.subTest(value=value):
                self.assertFalse(is_known(value))

    def test_explicit_low_level_is_not_misclassified_as_detected_pollen(self):
        self.assertTrue(is_known("low"))
        self.assertTrue(is_low("low"))
        self.assertFalse(is_present("low"))

    def test_moderate_and_high_levels_are_detected(self):
        self.assertTrue(is_present("moderate"))
        self.assertTrue(is_high("very high"))
        self.assertTrue(is_high("wysokie"))

    def test_numeric_scale_is_handled_conservatively(self):
        self.assertTrue(is_known("0"))
        self.assertFalse(is_present("0"))
        self.assertTrue(is_present("1"))
        self.assertFalse(is_high("3"))
        self.assertTrue(is_high("4"))


if __name__ == "__main__":
    unittest.main()
