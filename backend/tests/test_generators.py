from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from generators import (  # noqa: E402
    _parse_slides_text,
    _parse_stage_briefs,
    diagram_subject,
    diagram_title,
    education_stages,
    explicit_stage_names,
    parse_duration_seconds,
)


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

    def test_explicit_stage_names_needs_two_to_eight_items(self) -> None:
        self.assertEqual(explicit_stage_names("Frog stages: egg, tadpole"), ["egg", "tadpole"])
        self.assertEqual(explicit_stage_names("Frog stages: egg"), [])
        self.assertEqual(explicit_stage_names("Frog life cycle"), [])

    def test_explicit_stage_descriptions_keep_the_subject(self) -> None:
        stages = education_stages("Frog life cycle stages: egg, tadpole, froglet, adult frog")
        self.assertEqual(stages[0][0], "EGG")
        self.assertIn("Frog life cycle", stages[0][1])

    def test_diagram_title_drops_the_stage_list(self) -> None:
        self.assertEqual(
            diagram_title("Frog life cycle for classroom stages: egg, tadpole, froglet"),
            "FROG LIFE CYCLE FOR CLASSROOM",
        )

    def test_diagram_subject_survives_a_bare_prompt(self) -> None:
        self.assertEqual(diagram_subject("Water cycle"), "Water cycle")

    def test_stage_briefs_are_parsed_into_labels_and_visuals(self) -> None:
        raw = (
            "STAGE: Egg\nVISUAL: A jelly cluster of frog spawn floating in a pond.\n"
            "STAGE: Tadpole\nVISUAL: A small black tadpole with a long tail swimming.\n"
        )
        self.assertEqual(
            _parse_stage_briefs(raw),
            [
                ("EGG", "A jelly cluster of frog spawn floating in a pond."),
                ("TADPOLE", "A small black tadpole with a long tail swimming."),
            ],
        )

    def test_stage_briefs_ignore_a_stage_with_no_visual(self) -> None:
        raw = "STAGE: Egg\nSTAGE: Tadpole\nVISUAL: A tadpole swimming in a pond."
        self.assertEqual(_parse_stage_briefs(raw), [("TADPOLE", "A tadpole swimming in a pond.")])


if __name__ == "__main__":
    unittest.main()
