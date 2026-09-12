from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from generators import _parse_slides_text, education_stages, parse_duration_seconds  # noqa: E402


class GeneratorLogicTests(unittest.TestCase):
    def test_duration_defaults_to_30_seconds(self) -> None:
        self.assertEqual(parse_duration_seconds("create a nature video"), 30)

    def test_duration_reads_seconds(self) -> None:
        self.assertEqual(parse_duration_seconds("create a video for 10 sec"), 10)

    def test_duration_reads_minutes(self) -> None:
        self.assertEqual(parse_duration_seconds("make a 1.5 minute lesson"), 90)

    def test_duration_is_clamped_for_safety(self) -> None:
        self.assertEqual(parse_duration_seconds("make a 999 minute film"), 120)

    def test_butterfly_stages_are_complete_and_ordered(self) -> None:
        self.assertEqual(
            [label for label, _ in education_stages("Life cycle of butterfly")],
            ["EGG", "CATERPILLAR", "CHRYSALIS", "BUTTERFLY"],
        )

    def test_water_cycle_stages_are_complete_and_ordered(self) -> None:
        self.assertEqual(
            [label for label, _ in education_stages("Water cycle")],
            ["EVAPORATION", "CONDENSATION", "PRECIPITATION", "COLLECTION"],
        )

    def test_seven_stages_has_exactly_seven_distinct_labels(self) -> None:
        labels = [label for label, _ in education_stages("Seven stages of life")]
        self.assertEqual(len(labels), 7)
        self.assertEqual(len(set(labels)), 7)

    def test_custom_explicit_stages_are_preserved(self) -> None:
        labels = [label for label, _ in education_stages("Custom stages: idea, plan, build, test, launch")]
        self.assertEqual(labels, ["IDEA", "PLAN", "BUILD", "TEST", "LAUNCH"])

    def test_slide_text_is_parsed_into_titles_and_bullets(self) -> None:
        raw = "SLIDE: Egg Stage\n- Females lay eggs on leaves\n- Eggs hatch in days\nSLIDE: Caterpillar\n- It eats and grows"
        self.assertEqual(
            _parse_slides_text(raw),
            [
                ("Egg Stage", "Females lay eggs on leaves\nEggs hatch in days"),
                ("Caterpillar", "It eats and grows"),
            ],
        )

    def test_slide_text_tolerates_fences_numbering_and_blank_lines(self) -> None:
        raw = "```\nSLIDE - Overview\n\n1. First point\n* Second point\n\n```"
        self.assertEqual(_parse_slides_text(raw), [("Overview", "First point\nSecond point")])

    def test_slide_text_returns_nothing_for_unusable_output(self) -> None:
        self.assertEqual(_parse_slides_text("   "), [])


if __name__ == "__main__":
    unittest.main()
