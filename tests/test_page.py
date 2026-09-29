"""Failing-first tests for report/page.py's render_page seam.

These are direct, isolated tests of render_page(data) -> str, independent
of build_report -- see tests/test_ui_report.py for the integration-level
tests (U3, U4, U5, U6) that exercise the same rules through build_report's
actual written out/index.html.
"""
import unittest

from report.page import render_page

from tests._helpers import extract_embedded_json


def _sample_data(events=None):
    return {
        "timeline": [
            {"t": "2026-01-01T12:00:00Z", "macs": 2, "stuck": 0, "rpm": None},
            {"t": "2026-01-01T12:05:00Z", "macs": 2, "stuck": 0, "rpm": 22.0},
        ],
        "events": events if events is not None else [],
        "stuck_now": {"at": "2026-01-01T12:05:00Z", "count": 0, "by_chip": {}},
        "span": {
            "start": "2026-01-01T12:00:00Z",
            "end": "2026-01-01T12:05:00Z",
            "snapshots": 2,
        },
    }


class RenderPageContractTests(unittest.TestCase):
    def test_render_page_embeds_data_as_parseable_json_equal_to_input(self):
        data = _sample_data(events=[
            {
                "kind": "restart",
                "at": "2026-01-01T12:05:00Z",
                "label": "coordinator restart",
                "baseline_macs": 2,
                "min_macs_after": 0,
                "drop": 2,
                "recovery_minutes": 5.0,
                "requests_per_min_before": 22.0,
                "requests_per_min_after": 0.0,
                "stuck_before": 0,
                "stuck_after": 0,
                "stuck_carried": 0,
                "stuck_by_chip": {},
                "window": [
                    {"t": "2026-01-01T12:00:00Z", "macs": 2, "stuck": 0, "rpm": None},
                ],
                "chips_before": {"M3": 2},
            },
        ])

        html = render_page(data)

        self.assertIsInstance(html, str)
        embedded = extract_embedded_json(html)
        self.assertEqual(
            embedded, data,
            "the JSON embedded in the "
            "<script type=\"application/json\" id=\"wilt-data\"> "
            "block must parse back to exactly the data dict passed in",
        )

    def test_render_page_has_no_urls_or_external_script_or_link_tags(self):
        html = render_page(_sample_data())

        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script src", html)
        self.assertNotIn("<link", html)

    def test_render_page_zero_events_shows_no_events_line(self):
        html = render_page(_sample_data(events=[]))

        self.assertIn(
            "No restart or release was seen in the recorded span.", html,
        )


if __name__ == "__main__":
    unittest.main()
