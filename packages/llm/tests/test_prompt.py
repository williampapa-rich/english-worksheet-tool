"""PromptSpec 테스트 — frontmatter 로딩, 변수 치환."""

from __future__ import annotations

from pathlib import Path

import pytest
from llm.prompt import PromptSpec, _split_frontmatter


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """임시 프롬프트 디렉토리 (PROMPTS_DIR 환경변수로 override)."""
    d = tmp_path / "prompts"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def set_prompts_dir(prompts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PROMPTS_DIR 환경변수를 임시 디렉토리로 설정."""
    monkeypatch.setenv("PROMPTS_DIR", str(prompts_dir))


def _write_prompt(prompts_dir: Path, name: str, content: str) -> None:
    (prompts_dir / f"{name}.md").write_text(content, encoding="utf-8")


class TestSplitFrontmatter:
    def test_no_frontmatter(self) -> None:
        front, body = _split_frontmatter("Hello world")
        assert front is None
        assert body == "Hello world"

    def test_with_frontmatter(self) -> None:
        content = "---\nkey: value\n---\nBody text"
        front, body = _split_frontmatter(content)
        assert front is not None
        assert "key: value" in front
        assert "Body text" in body

    def test_frontmatter_no_closing(self) -> None:
        content = "---\nkey: value\n"
        front, body = _split_frontmatter(content)
        # 닫히는 --- 없으면 frontmatter 없는 것으로 처리
        assert front is None

    def test_empty_frontmatter(self) -> None:
        content = "---\n---\nBody"
        front, body = _split_frontmatter(content)
        assert front is not None
        assert "Body" in body


class TestPromptSpecRender:
    def test_render_no_variables(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "simple", "---\n---\nHello world")
        spec = PromptSpec(template_id="simple")
        assert spec.render() == "Hello world"

    def test_render_with_variables(self, prompts_dir: Path) -> None:
        _write_prompt(
            prompts_dir, "template", "---\n---\nHello {{name}}, you have {{count}} items."
        )
        spec = PromptSpec(template_id="template", variables={"name": "Alice", "count": "5"})
        result = spec.render()
        assert result == "Hello Alice, you have 5 items."

    def test_render_missing_variable_raises(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "needs_var", "---\n---\nHello {{name}} and {{other}}.")
        spec = PromptSpec(template_id="needs_var", variables={"name": "Alice"})
        with pytest.raises(ValueError, match="치환되지 않은 변수"):
            spec.render()

    def test_render_file_not_found(self) -> None:
        spec = PromptSpec(template_id="nonexistent_template_xyz")
        with pytest.raises(FileNotFoundError):
            spec.render()

    def test_render_no_frontmatter(self, prompts_dir: Path) -> None:
        """frontmatter 없는 파일도 정상 처리."""
        _write_prompt(prompts_dir, "no_front", "Plain text {{var}}")
        spec = PromptSpec(template_id="no_front", variables={"var": "OK"})
        assert spec.render() == "Plain text OK"


class TestPromptSpecFrontmatter:
    def test_load_frontmatter_with_fields(self, prompts_dir: Path) -> None:
        content = "---\nmodel_hint: claude-test\ndescription: 테스트\nversion: 1\n---\nBody"
        _write_prompt(prompts_dir, "with_meta", content)
        spec = PromptSpec(template_id="with_meta")
        fm = spec.load_frontmatter()
        assert fm.model_hint == "claude-test"
        assert fm.description == "테스트"
        assert fm.version == 1

    def test_load_frontmatter_empty(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "no_meta", "---\n---\nBody")
        spec = PromptSpec(template_id="no_meta")
        fm = spec.load_frontmatter()
        assert fm.model_hint is None
        assert fm.description is None

    def test_load_frontmatter_no_front_block(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "plain", "Just body text")
        spec = PromptSpec(template_id="plain")
        fm = spec.load_frontmatter()
        assert fm.model_hint is None

    def test_load_frontmatter_extra_field_allowed(self, prompts_dir: Path) -> None:
        """알려지지 않은 frontmatter 필드는 허용 (extra='allow')."""
        content = "---\ncustom_field: value\n---\nBody"
        _write_prompt(prompts_dir, "extra_field", content)
        spec = PromptSpec(template_id="extra_field")
        fm = spec.load_frontmatter()
        # extra='allow' 이므로 ValidationError 발생 안 함
        assert fm is not None
