"""L0: the functional/style boundary of the web UI (docs/ui.md).

Views build semantic components and carry visual state in data attributes: no inline styles,
no innerHTML, no colour or size words in class strings. css/base.css holds structure only;
css/themes/*.css hold tokens, colours, fonts and effects only.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "viwo" / "web"
VIEW_FILES = sorted((WEB / "js" / "views").glob("*.js")) + [WEB / "js" / "landing.js"]
COLOR_OR_SIZE = re.compile(
    r"\b(red|cyan|amber|coral|blue|green|white|black|grey|gray|big|huge|tiny|px|bold|wide)\b"
)
CLASS_STRING = re.compile(r"class:\s*(\"[^\"]*\"|'[^']*'|`[^`]*`)")
BASE_FORBIDDEN = re.compile(
    r"(^|[\s;{])(color:|background:[^;]*(rgb|#|var\(--(?!c\b|poly|top|rail|p\b|w\b|h\b|i\b|n\b))"
    r"|font-family:|text-shadow:|box-shadow:)"
)
THEME_FORBIDDEN = re.compile(r"(^|[\s;{])(display:|grid-template[\w-]*:|position:)")


class ViewBoundaryTests(unittest.TestCase):
    def test_views_have_no_inline_styles_or_markup_injection(self) -> None:
        for path in VIEW_FILES:
            text = path.read_text(encoding="utf-8")
            for bad in ("style:", ".style.", "innerHTML", "outerHTML", "insertAdjacentHTML"):
                self.assertNotIn(
                    bad, text, f"{path.name}: views must not use {bad}; use a component"
                )

    def test_views_use_component_class_names_only(self) -> None:
        for path in VIEW_FILES:
            for match in CLASS_STRING.finditer(path.read_text(encoding="utf-8")):
                literal = match.group(1)
                hit = COLOR_OR_SIZE.search(literal)
                self.assertIsNone(hit, f"{path.name}: class {literal} carries a colour/size word")

    def test_views_never_append_null(self) -> None:
        for path in VIEW_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text, r"\.append\([^)]*\?\s*[^:]+:\s*null", f"{path.name}: use add()/fill()"
            )


class StylesheetBoundaryTests(unittest.TestCase):
    def test_index_links_base_and_a_theme(self) -> None:
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="css/base.css"', html)
        self.assertIn('id="theme-link"', html)
        self.assertFalse(
            (WEB / "viwo.css").exists(), "the single stylesheet was split; do not bring it back"
        )

    def test_base_has_no_colours_fonts_or_effects(self) -> None:
        for n, line in enumerate(
            (WEB / "css" / "base.css").read_text(encoding="utf-8").splitlines(), 1
        ):
            if line.lstrip().startswith("/*"):
                continue
            self.assertIsNone(BASE_FORBIDDEN.search(line), f"base.css:{n}: {line.strip()[:90]}")

    def test_themes_have_no_layout(self) -> None:
        themes = sorted((WEB / "css" / "themes").glob("*.css"))
        self.assertGreaterEqual(len(themes), 2, "at least two themes prove the boundary")
        for theme in themes:
            for n, line in enumerate(theme.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("/*"):
                    continue
                self.assertIsNone(
                    THEME_FORBIDDEN.search(line), f"{theme.name}:{n}: {line.strip()[:90]}"
                )

    def test_every_theme_defines_the_tokens(self) -> None:
        wanted = ("--bg:", "--red:", "--text:", "--line:", "--f-head:", "--f-body:", "--f-mono:")
        for theme in (WEB / "css" / "themes").glob("*.css"):
            text = theme.read_text(encoding="utf-8")
            for token in wanted:
                self.assertIn(token, text, f"{theme.name} lacks {token}")


if __name__ == "__main__":
    unittest.main()
