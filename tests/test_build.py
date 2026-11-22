import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import ROOT, build, metadata


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "web", self.root / "web")
        shutil.copytree(ROOT / "data", self.root / "data")
        shutil.copyfile(ROOT / "tool.json", self.root / "tool.json")
        shutil.copyfile(ROOT / "README.md", self.root / "README.md")

    def edit(self, **changes):
        tool = json.loads((self.root / "tool.json").read_text())
        tool.update(changes)
        (self.root / "tool.json").write_text(json.dumps(tool))

    def test_build_is_scoped_to_web_and_escapes_metadata(self):
        (self.root / "private.txt").write_text("must not publish")
        self.edit(title='<img src=x onerror="bad()">')
        build(self.root)
        page = (self.root / "dist/index.html").read_text()
        self.assertIn('&lt;img', page)
        self.assertNotIn('<img', page)
        self.assertNotIn('{{', page)
        self.assertRegex(page, r'href="\./style\.[a-f0-9]{16}\.css"')
        self.assertFalse((self.root / "dist/private.txt").exists())
        self.assertTrue((self.root / "dist/.nojekyll").exists())

    def test_asset_urls_change_with_dependencies_and_resolve_at_the_project_path(self):
        def assets():
            build(self.root)
            output = self.root / "dist"
            page = (output / "index.html").read_text()
            app = re.search(r'src="\./(app\.[a-f0-9]{16}\.mjs)"', page).group(1)
            style = re.search(r'href="\./(style\.[a-f0-9]{16}\.css)"', page).group(1)
            model = re.search(r"\./(model\.[a-f0-9]{16}\.mjs)", (output / app).read_text()).group(1)
            for name in (app, style, model):
                self.assertTrue((output / name).is_file())
            self.assertNotIn('./app.mjs', page)
            self.assertNotIn('./model.mjs', (output / app).read_text())
            self.assertFalse((output / 'model.mjs').exists())
            return app, model, style

        before = assets()
        self.assertEqual(before, assets(), 'Unchanged source must build identical asset URLs')
        model_path = self.root / 'web/model.mjs'
        model_path.write_text(model_path.read_text() + '\n// New model version for the cache regression test.\n')
        after = assets()
        self.assertNotEqual(before[0], after[0], 'The app URL must change when its model dependency changes')
        self.assertNotEqual(before[1], after[1])
        self.assertEqual(before[2], after[2])
        style_path = self.root / 'web/style.css'
        style_path.write_text(style_path.read_text() + '\n/* New stylesheet version for the cache regression test. */\n')
        styled = assets()
        self.assertEqual(after[:2], styled[:2])
        self.assertNotEqual(after[2], styled[2])

    def test_reporting_is_scoped_to_initialized_coolcode_tools(self):
        for owner, slug, enabled in [
            ("jsdyer", "coolcode-tool-template", False),
            ("another-owner", "my-tool", False),
            ("jsdyer", "my-tool", True),
        ]:
            with self.subTest(owner=owner, slug=slug):
                self.edit(id=slug, url=f"/{slug}/", source=f"https://github.com/{owner}/{slug}")
                build(self.root)
                page = (self.root / "dist/index.html").read_text()
                self.assertEqual('/assets/tool-metrics.js' in page, enabled)
                self.assertEqual(f'https://coolcode.ca/report/?tool={slug}' in page, enabled)
                self.assertNotIn("{{", page)

    def test_url_matches_tool_id(self):
        self.edit(url="/different/")
        with self.assertRaises(ValueError): metadata(self.root)

    def test_requires_a_source_sentence_and_a_guide_note(self):
        (self.root / "README.md").write_text("# A tool")
        with self.assertRaisesRegex(ValueError, "README note"):
            metadata(self.root)
        self.edit(data_info={"mode": "local", "detail": ""})
        with self.assertRaisesRegex(ValueError, "homepage card"):
            metadata(self.root)

    def test_browser_access_is_explicit(self):
        self.edit(access="install")
        with self.assertRaisesRegex(ValueError, "immediately usable"):
            metadata(self.root)

    def test_failed_build_keeps_existing_output(self):
        build(self.root)
        existing = (self.root / "dist/index.html").read_bytes()
        self.edit(source="javascript:bad()")
        with self.assertRaises(ValueError): build(self.root)
        self.assertEqual((self.root / "dist/index.html").read_bytes(), existing)


if __name__ == "__main__": unittest.main()
