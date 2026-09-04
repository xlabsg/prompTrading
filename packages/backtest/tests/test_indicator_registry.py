import unittest
from backtest.indicators import get_catalog, filter_catalog, IndicatorMeta


class TestIndicatorRegistry(unittest.TestCase):
    def test_get_catalog_structure(self):
        catalog = get_catalog()
        self.assertIsInstance(catalog, dict)
        self.assertGreaterEqual(len(catalog), 20)

        # Ensure keys match meta.name
        for name, meta in catalog.items():
            self.assertIsInstance(meta, IndicatorMeta)
            self.assertEqual(name, meta.name)
            self.assertTrue(callable(meta.func))
            self.assertIsInstance(meta.inputs, list)
            self.assertIsInstance(meta.tags, list)
            self.assertIn(meta.role, {"trigger", "confirmation", "filter", "sizing", "transform"})

    def test_filter_by_tag(self):
        crypto_inds = filter_catalog(tag="crypto")
        self.assertIn("funding_rate_zscore", crypto_inds)
        self.assertIn("oi_momentum", crypto_inds)
        self.assertNotIn("sma", crypto_inds)

    def test_filter_by_role(self):
        triggers = filter_catalog(role="trigger")
        self.assertIn("supertrend", triggers)
        self.assertIn("sma", triggers)
        self.assertNotIn("funding_rate_zscore", triggers)

        sizings = filter_catalog(role="sizing")
        self.assertIn("atr", sizings)

    def test_filter_by_input(self):
        vol_inds = filter_catalog(input_col="volume")
        self.assertIn("vwap", vol_inds)
        self.assertIn("cmf", vol_inds)
        self.assertNotIn("sma", vol_inds)

    def test_serialization(self):
        catalog = get_catalog()
        st = catalog["supertrend"]
        d = st.to_dict()
        self.assertEqual(d["name"], "supertrend")
        self.assertEqual(d["role"], "trigger")
        self.assertIn("breakout", d["tags"])
        self.assertIn("close", d["inputs"])


if __name__ == "__main__":
    unittest.main()
