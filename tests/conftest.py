"""pytest 公共 fixture。

约定：**依赖外部软件（Word / WPS / LibreOffice）的用例必须能自动跳过**，
绝不让"开发机没装 Office"变成测试失败。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.fixtures.builders import build_all


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, Path]:
    """会话级样本文件（生成一次，多处复用）。"""
    directory = tmp_path_factory.mktemp("samples")
    return build_all(directory)


@pytest.fixture
def raw_settings(tmp_path) -> dict:
    """指向 tmp 目录的配置原始值。"""
    return {
        "paths": {
            "input_directory": str(tmp_path / "input"),
            "output_directory": str(tmp_path / "output"),
            "log_directory": str(tmp_path / "logs"),
            "temp_directory": str(tmp_path / "temp"),
        },
        "conversion": {
            "conflict_policy": "rename",
            "pdf_backend_preference": "auto",
            "max_workers": "2",
            "office_timeout_seconds": "120",
            "keep_structure": "true",
            "xlsx_csv_mode": "sheets",
            "extract_media": "true",
        },
        "defaults": {
            "default_target": "pdf",
            "target_docx": "pdf",
            "target_pdf": "docx",
            "target_xlsx": "csv",
            "target_md": "docx",
            "target_html": "pdf",
            "target_txt": "docx",
            "target_csv": "xlsx",
        },
    }


@pytest.fixture
def settings(tmp_path, raw_settings):
    from docmorph.settings.schema import build_settings

    (tmp_path / "logs").mkdir(exist_ok=True)
    return build_settings(raw_settings, [])


@pytest.fixture
def engine(settings):
    """真实后端的引擎。"""
    from docmorph.engine import ConversionEngine

    return ConversionEngine(settings=settings)


@pytest.fixture
def service(tmp_path, raw_settings):
    """应用服务（临时配置，日志写入 tmp）。"""
    from docmorph.services import ApplicationService
    from docmorph.settings import ConfigManager
    from docmorph.settings.schema import build_settings, render_settings_ini

    config_path = tmp_path / "config.ini"
    config_path.write_text(render_settings_ini(build_settings(raw_settings, [])), encoding="utf-8")
    config = ConfigManager(str(config_path))
    svc = ApplicationService(config=config)
    yield svc
    svc.shutdown()


def has_backend(backend_id: str) -> bool:
    """该后端在当前环境是否可用（供 skipif 使用）。"""
    from docmorph.capability import detect

    return detect().available(backend_id)


OFFICE_SKIP = pytest.mark.skipif(
    not has_backend("word"), reason="需要 Microsoft Word（当前环境不可用）"
)
PANDOC_SKIP = pytest.mark.skipif(
    not has_backend("pandoc"), reason="需要 pandoc（当前环境不可用）"
)


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_office: 需要 Microsoft Office")
    config.addinivalue_line("markers", "needs_pandoc: 需要 pandoc")
    config.addinivalue_line("markers", "slow: 耗时较长的真实转换")
