"""Real-browser tests: the widgets rendered in Chromium and driven with clicks and typing.

These use pytest-ipywidgets (from the Solara project): the widgets live in this Python
process, a Solara server renders them with the standard ipywidgets front end, and Playwright
drives a headless Chromium. They check what the other tests can't: that the table actually
renders, and that browser events reach Python and results come back to the page.

    pip install -e ".[ui]"
    playwright install chromium
    pytest -m ui
"""

import time

import pytest

pytest.importorskip("playwright")
pytest.importorskip("solara")

from IPython.display import display  # noqa: E402

from ipyrowtable.examples.conduction import LayerStack  # noqa: E402

pytestmark = pytest.mark.ui


def wait_until(predicate, timeout=10.0):
    """Browser events reach Python asynchronously; poll until `predicate()` is true."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.05)


def show(page, stack):
    display(stack)
    page.locator(".ipyrowtable-grid").wait_for()
    return page


def test_table_renders(solara_test, page_session):
    page = show(page_session, LayerStack())
    for header in ("Thickness (mm)", "Conductance (W/m²·K)", "Temperature (°C)"):
        page.locator(".ipyrowtable-header", has_text=header).wait_for()
    page.locator("text=— top surface —").wait_for()
    assert page.locator(".ipyrowtable-thickness input").count() == 2
    page.locator(".ipyrowtable-message", has_text="Heat flux q = 63.99 W/m²").wait_for()


def test_add_and_remove_rows_with_the_mouse(solara_test, page_session):
    stack = LayerStack()
    page = show(page_session, stack)

    page.locator(".ipyrowtable-add").click()
    wait_until(lambda: len(stack) == 3)
    page.locator(".ipyrowtable-thickness input").nth(2).wait_for()

    page.locator(".ipyrowtable-remove").first.click()
    wait_until(lambda: len(stack) == 2)
    assert stack.layers[0][0] == "Fiberglass insulation"
    wait_until(lambda: page.locator(".ipyrowtable-thickness input").count() == 2)


def test_typing_a_thickness_recomputes(solara_test, page_session):
    stack = LayerStack()
    page = show(page_session, stack)

    box = page.locator(".ipyrowtable-thickness input").nth(1)
    box.fill("100")
    box.press("Enter")
    wait_until(lambda: stack.layers[1][1] == 100.0)
    # 10 mm steel + 100 mm fiberglass, 100 °C / 20 °C: q = 80 / (0.000165 + 2.5) = 31.998 W/m²
    page.locator(".ipyrowtable-message", has_text="Heat flux q = 32.00 W/m²").wait_for()


def test_units_toggle_in_the_browser(solara_test, page_session):
    stack = LayerStack()
    page = show(page_session, stack)

    page.locator(".ipyrowtable-units button", has_text="Imperial").click()
    wait_until(lambda: stack.units.name == "Imperial")
    page.locator(".ipyrowtable-header", has_text="Thickness (in)").wait_for()
    page.locator(".ipyrowtable-temperature", has_text="211.98").wait_for()
    assert page.locator(".ipyrowtable-temperature-first input").input_value() == "212"


def test_invalid_input_shows_message(solara_test, page_session):
    stack = LayerStack()
    page = show(page_session, stack)

    box = page.locator(".ipyrowtable-thickness input").first
    box.fill("0")
    box.press("Enter")
    page.locator(".ipyrowtable-message",
                 has_text="Every layer needs a thickness greater than zero.").wait_for()
    assert stack.results is None


def test_profile_plot_renders_and_updates(solara_test, page_session):
    pytest.importorskip("matplotlib")
    from ipyrowtable.examples.conduction import layer_stack_app

    app = layer_stack_app(plot_options={"dpi": 80})
    display(app)
    img = page_session.locator("img.ipyrowtable-figure")
    img.wait_for()
    width = img.evaluate("el => el.naturalWidth")
    assert width > 100  # a real, decoded PNG

    first = img.get_attribute("src")
    page_session.locator(".ipyrowtable-add").click()
    wait_until(lambda: img.get_attribute("src") != first)  # redrawn after the change
