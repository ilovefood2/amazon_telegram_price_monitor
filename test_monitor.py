import json
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import monitor as m


CORE = "#corePrice_feature_div .a-price.apex-pricetopay-value"
DISPLAY = "#corePriceDisplay_desktop_feature_div .a-price.apex-pricetopay-value"
PRODUCT = {
    "key": "bench", "name": "Bench", "parser": "amazon",
    "url": "https://www.amazon.ca/dp/B08YWHN79N",
    "target_price": 229.99, "currency": "CAD", "repeat_alert_hours": 0,
    "price_selectors": [],
}
CASHBACK = {
    "key": "store", "name": "Store", "url": "https://www.rakuten.ca/store",
    "threshold_percent": 10, "comparison": "gt", "repeat_alert_hours": 0,
}


def element(text="", children=None, visible=True, classes="a-price", strike=None):
    node = Mock()
    node.is_displayed.return_value = visible
    attrs = {"textContent": text, "class": classes, "data-a-strike": strike}
    node.get_attribute.side_effect = attrs.get
    node.find_elements.side_effect = lambda by, selector: (children or {}).get(selector, [])
    node.text = text
    return node


def driver(matches):
    browser = Mock()
    browser.page_source = "<html>product page</html>"
    browser.find_elements.side_effect = lambda by, selector: matches.get(selector, [])
    return browser


class AmazonPriceTests(unittest.TestCase):
    def test_blank_accessibility_price_uses_whole_and_fraction(self):
        node = element(children={
            ".a-offscreen": [element(" ")],
            ".a-price-whole": [element("1,279.")],
            ".a-price-fraction": [element("99")],
        })
        self.assertEqual(m.extract_amazon_price(driver({DISPLAY: [node]}))[0], 1279.99)

    def test_struck_and_hidden_prices_are_rejected(self):
        for node in [element("$329.99", classes="a-price a-text-price"),
                     element("$329.99", strike="true"),
                     element("$199.99", visible=False)]:
            with self.subTest(node=node):
                self.assertIsNone(m.extract_amazon_price(driver({CORE: [node]})))

    def test_recommendation_prices_are_not_searched(self):
        self.assertIsNone(m.extract_amazon_price(driver({
            "span.a-price span.a-offscreen": [element("$49.99")],
        })))

    def test_current_price_wins_over_list_price(self):
        self.assertEqual(m.extract_amazon_price(driver({
            CORE: [element("$279.99")],
            DISPLAY: [element("$329.99", classes="a-price a-text-price")],
        }))[0], 279.99)

    def test_amazon_does_not_fall_through_to_generic_metadata(self):
        with patch.object(m, "wait_for_product_page"), \
             patch.object(m, "ELEMENT_WAIT_SECONDS", 0), \
             patch.object(m, "extract_jsonld_product_price") as metadata:
            with self.assertRaisesRegex(RuntimeError, "current Amazon offer"):
                m.get_product_price(driver({}), PRODUCT)
            metadata.assert_not_called()

    def test_challenge_is_rejected_before_configured_price(self):
        browser = driver({})
        browser.page_source = "Sorry, we just need to make sure"
        with patch.object(m, "wait_for_product_page"), \
             patch.object(m, "extract_from_configured_selectors") as configured:
            with self.assertRaisesRegex(RuntimeError, "challenge"):
                m.get_product_price(browser, PRODUCT)
            configured.assert_not_called()


class ConfiguredPriceTests(unittest.TestCase):
    selector = "script[type='application/ld+json']"
    pattern = (
        r'"sku"\s*:\s*"5339125"[\s\S]*?"offers"\s*:\s*\{'
        r'[^{}]*"priceCurrency"\s*:\s*"CAD"[^{}]*"price"\s*:\s*'
        r'([0-9]+(?:\.[0-9]{1,2})?)\s*\}'
    )

    def product(self):
        return dict(PRODUCT, parser="generic", target_price=699.99,
                    price_selectors=[self.selector], price_regex=self.pattern)

    def page(self, sku="5339125", currency="CAD", price=799.99):
        data = {"@type": "Product", "sku": sku,
                "offers": {"priceCurrency": currency, "price": price}}
        return driver({self.selector: [element(json.dumps(data))]})

    def test_costco_matches_the_requested_product_and_currency(self):
        with patch.object(m, "wait_for_product_page"):
            self.assertEqual(m.get_product_price(self.page(), self.product())[1], 799.99)

    def test_invalid_costco_data_cannot_fall_back_to_another_price(self):
        for kwargs in [{"sku": "other-item"}, {"currency": "USD"}, {"price": 0}]:
            with self.subTest(kwargs=kwargs), \
                 patch.object(m, "wait_for_product_page"), \
                 patch.object(m, "extract_jsonld_product_price", return_value=(40, "other", "40")) as automatic:
                with self.assertRaisesRegex(RuntimeError, "Configured price selector"):
                    m.get_product_price(self.page(**kwargs), self.product())
                automatic.assert_not_called()

    def test_costco_requires_a_price_strictly_below_700(self):
        self.assertFalse(m.should_alert({}, 700, 699.99, 0))
        self.assertTrue(m.should_alert({}, 699.99, 699.99, 0))


class MonitorLoopTests(unittest.TestCase):
    def run_cycle(self, state, products=None, cashback=None,
                  product_error=None, cashback_error=None, send_error=None):
        # Run one real loop; interrupt only its final scheduling sleep.
        with ExitStack() as stack:
            stack.enter_context(patch.object(m, "log"))
            mocks = {}
            values = {
                "load_state": {"return_value": state},
                "load_products": {"side_effect": product_error} if product_error else {"return_value": products or []},
                "load_cashback_monitors": {"side_effect": cashback_error} if cashback_error else {"return_value": cashback or []},
                "build_driver": {},
                "get_product_price": {"return_value": ("Bench", 219.99)},
                "get_rakuten_cashback_rate": {"return_value": 12},
                "send_telegram": {"side_effect": send_error},
                "save_state": {},
            }
            for name, kwargs in values.items():
                mocks[name] = stack.enter_context(patch.object(m, name, **kwargs))
            stack.enter_context(patch.object(m.time, "sleep", side_effect=KeyboardInterrupt))
            with self.assertRaises(KeyboardInterrupt):
                m.run()
            return mocks

    def test_cashback_config_error_does_not_block_products(self):
        mocks = self.run_cycle({"products": {}, "cashback": {}}, products=[PRODUCT],
                               cashback_error=ValueError("bad cashback config"))
        mocks["get_product_price"].assert_called_once()

    def test_product_config_error_does_not_block_cashback(self):
        mocks = self.run_cycle({"products": {}, "cashback": {}}, cashback=[CASHBACK],
                               product_error=ValueError("bad product config"))
        mocks["get_rakuten_cashback_rate"].assert_called_once()

    def test_failed_recrossing_product_alert_is_retried(self):
        state = {"products": {"bench": {"below_target": False, "last_alert_price": 199.99}}, "cashback": {}}
        self.run_cycle(state, products=[PRODUCT], send_error=RuntimeError("delivery failed"))
        self.assertFalse(state["products"]["bench"]["below_target"])
        mocks = self.run_cycle(state, products=[PRODUCT])
        mocks["send_telegram"].assert_called_once()
        self.assertTrue(state["products"]["bench"]["below_target"])
        self.assertEqual(state["products"]["bench"]["last_alert_price"], 219.99)
        self.assertNotIn("last_error", state["products"]["bench"])

    def test_failed_recrossing_cashback_alert_is_retried(self):
        state = {"products": {}, "cashback": {"store": {"above_threshold": False, "last_alert_rate": 15}}}
        self.run_cycle(state, cashback=[CASHBACK], send_error=RuntimeError("delivery failed"))
        self.assertFalse(state["cashback"]["store"]["above_threshold"])
        mocks = self.run_cycle(state, cashback=[CASHBACK])
        mocks["send_telegram"].assert_called_once()
        self.assertTrue(state["cashback"]["store"]["above_threshold"])
        self.assertNotIn("last_error", state["cashback"]["store"])

    def test_zero_repeat_still_allows_lower_prices(self):
        self.assertFalse(m.should_alert({"below_target": True, "last_alert_price": 229.99}, 229.99, 229.99, 0))
        self.assertTrue(m.should_alert({"below_target": True, "last_alert_price": 229.99}, 219.99, 229.99, 0))


if __name__ == "__main__":
    unittest.main()
