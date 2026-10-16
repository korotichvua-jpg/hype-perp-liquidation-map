"""UI Full End-to-End Test Suite using Playwright.

Executes comprehensive browser-driven validation of:
1. Terminal page load, WebSocket telemetry header, spot and OI badges.
2. Interactive Liquidation Waterfall Simulator (range slider & preset buttons).
3. Modern Fire Tape HUD (rolling buy/sell delta bar, whale filters, pause/play).
4. Order Flow Matrix Drawer (3-column layout, drawer toggle interaction).
5. Air Pocket card and resting orderbook depth indicators.
6. Detailed system & telemetry footer (folder path, internal/external IP, AI model).
7. Liquidation Map (/map) interactive Plotly container and telemetry footer.
8. Responsive mobile viewport rendering and error-free execution.
"""
import re
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, Page, Browser, expect


@pytest.fixture(scope="module")
def browser_instance():
    """Launch headless Chromium browser for the module."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser_instance: Browser) -> Page:
    """Create a fresh browser page with standard desktop viewport."""
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    pg = context.new_page()
    yield pg
    context.close()


class TestPlaywrightTerminalE2E:
    """End-to-end tests for the /terminal Pro Liquidation Terminal dashboard."""

    def test_terminal_page_load_and_header_metrics(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        # Verify page title
        assert "Liquidation Terminal" in page.title()

        # Verify WebSocket telemetry badge
        ws_badge = page.locator("#wsStatusBadge")
        assert ws_badge.is_visible()
        ws_text = page.locator("#wsStatusText").inner_text()
        assert "LIVE" in ws_text or "CONNECTED" in ws_text or "POLLING" in ws_text

        # Verify Spot badge & OI badge
        spot_badge = page.locator("#spotBadge")
        assert spot_badge.is_visible()
        assert "$" in spot_badge.inner_text()

        oi_badge = page.locator("#termOiBadge")
        assert oi_badge.is_visible()
        assert "M" in oi_badge.inner_text()

    def test_waterfall_simulator_slider_interaction(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        slider = page.locator("#priceSlider")
        assert slider.is_visible()
        initial_price = float(slider.input_value())

        # Move price slider downwards to trigger long liquidation cascade
        target_down = round(initial_price * 0.90, 2)
        page.evaluate("(val) => { const s = document.getElementById('priceSlider'); s.value = val; s.dispatchEvent(new Event('input')); }", target_down)
        quantized_price = float(slider.input_value())

        # Verify target price display updated
        target_display = page.locator("#targetPriceDisplay")
        expect(target_display).to_contain_text(f"${quantized_price:.2f}")

        # Verify wiped USD updated from $0.0M to non-zero cascade
        wiped_display = page.locator("#wipedUsdDisplay")
        expect(wiped_display).not_to_have_text("$0.0M")
        wiped_text = wiped_display.inner_text()
        assert "$" in wiped_text and "M" in wiped_text

        # Verify severity risk badge updated
        risk_badge = page.locator("#riskBadge")
        assert risk_badge.is_visible()
        assert "CASCADE" in risk_badge.inner_text() or "RISK" in risk_badge.inner_text()

        # Verify depth canvas element is rendered
        canvas = page.locator("#depthCanvas")
        assert canvas.is_visible()
        box = canvas.bounding_box()
        assert box is not None and box["width"] > 200 and box["height"] > 100

    def test_waterfall_preset_buttons_interaction(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        # Click -15% preset button
        btn_minus_15 = page.locator("button.preset-btn:has-text('-15%')")
        assert btn_minus_15.is_visible()
        btn_minus_15.click()

        pct_badge = page.locator("#pctBadge")
        expect(pct_badge).to_contain_text("-15")

        # Click +15% preset button
        btn_plus_15 = page.locator("button.preset-btn:has-text('+15%')")
        assert btn_plus_15.is_visible()
        btn_plus_15.click()

        expect(pct_badge).to_contain_text("+15")

    def test_fire_tape_hud_filters_and_order_flow_drawer(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        # 1. Fire Tape HUD island & delta bar
        tape_island = page.locator("#tapeIsland")
        assert tape_island.is_visible()
        delta_buy_bar = page.locator("#deltaBuyBar")
        delta_sell_bar = page.locator("#deltaSellBar")
        assert delta_buy_bar.is_visible() and delta_sell_bar.is_visible()

        # 2. Filter buttons active toggle
        filter_whales = page.locator("#filterWhales")
        filter_liqs = page.locator("#filterLiqs")
        filter_all = page.locator("#filterAll")

        filter_whales.click()
        expect(filter_whales).to_have_class(re.compile(r"active"))
        expect(filter_all).not_to_have_class(re.compile(r"active"))

        filter_liqs.click()
        expect(filter_liqs).to_have_class(re.compile(r"active"))
        expect(filter_whales).not_to_have_class(re.compile(r"active"))

        filter_all.click()
        expect(filter_all).to_have_class(re.compile(r"active"))

        # 3. Order Flow Matrix Drawer Toggle
        drawer_btn = page.locator("#drawerToggleBtn")
        assert drawer_btn.is_visible()

        drawer = page.locator("#tapeDrawer")
        # Initially hidden
        assert not drawer.is_visible()

        # Open Drawer
        drawer_btn.click()
        page.wait_for_selector("#tapeDrawer", state="visible", timeout=2000)
        assert drawer.is_visible()

        # Verify 3 matrix column counters are present and visible
        assert page.locator("#countAllPrints").is_visible()
        assert page.locator("#countWhalePrints").is_visible()
        assert page.locator("#countLiqPrints").is_visible()
        assert page.locator("#drawerListAll").count() == 1
        assert page.locator("#drawerListWhales").count() == 1
        assert page.locator("#drawerListLiqs").count() == 1

        # Close Drawer
        drawer_btn.click()
        page.wait_for_selector("#tapeDrawer", state="hidden", timeout=2000)
        assert not drawer.is_visible()

    def test_air_pocket_card_and_depth_metrics(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        badge = page.locator("#airPocketCardBadge")
        assert badge.is_visible()

        main_status = page.locator("#termAirPocketMain")
        assert main_status.is_visible()
        assert len(main_status.inner_text().strip()) > 0

        bids_2 = page.locator("#termBids2")
        asks_2 = page.locator("#termAsks2")
        assert bids_2.is_visible() and "$" in bids_2.inner_text()
        assert asks_2.is_visible() and "$" in asks_2.inner_text()

    def test_telemetry_footer_integrity(self, page: Page, server_url: str):
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        # Scroll to bottom to inspect footer
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        footer = page.locator("footer")
        assert footer.is_visible()

        footer_text = footer.inner_text()
        assert "D:\\projects\\N1" in footer_text or "D:/projects/N1" in footer_text
        assert "192.168.1.12" in footer_text
        assert "83.5.208.192" in footer_text
        assert "Antigravity 2.0" in footer_text
        assert "Gemini 2.5 Pro" in footer_text


class TestPlaywrightLiquidationMapE2E:
    """End-to-end tests for the /map Plotly Liquidation Map dashboard."""

    def test_liquidation_map_page_load_and_plotly_container(self, page: Page, server_url: str):
        page.goto(f"{server_url}/map", wait_until="networkidle")

        # Verify sticky header
        header = page.locator("#liveTelemetryHeader")
        assert header.is_visible()

        spot_badge = page.locator("#spotPriceBadge")
        assert spot_badge.is_visible() and "$" in spot_badge.inner_text()

        air_pill = page.locator("#airPocketPill")
        assert air_pill.is_visible()

        # Verify interactive Plotly graph container rendered
        plotly_div = page.locator(".js-plotly-plot, .plotly-graph-div").first
        page.wait_for_selector(".js-plotly-plot, .plotly-graph-div", timeout=5000)
        assert plotly_div.is_visible()

        # Verify telemetry footer on /map
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        footer = page.locator("footer")
        assert footer.is_visible()
        footer_text = footer.inner_text()
        assert "192.168.1.12" in footer_text
        assert "83.5.208.192" in footer_text


class TestPlaywrightResponsiveMobileE2E:
    """End-to-end tests for mobile responsive layout."""

    def test_mobile_viewport_rendering_and_layout(self, browser_instance: Browser, server_url: str):
        # Emulate iPhone 14 Pro
        context = browser_instance.new_context(
            viewport={"width": 393, "height": 852},
            is_mobile=True,
            has_touch=True
        )
        page = context.new_page()
        page.goto(f"{server_url}/terminal", wait_until="networkidle")

        # Verify header spot badge and slider remain accessible on mobile
        assert page.locator("#spotBadge").is_visible()
        assert page.locator("#priceSlider").is_visible()
        assert page.locator("#airPocketCardBadge").is_visible()

        # Verify footer renders on mobile
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        assert page.locator("footer").is_visible()

        context.close()
