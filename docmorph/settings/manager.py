"""配置管理器：分层合并 + 旧配置迁移 + 校验。

读取优先级（低 → 高）::

    代码默认值 < 用户配置文件 < DOCMORPH_* 环境变量 < 调用方传入的覆盖值(CLI/UI)

设计要点：

* 配置键的大小写与 section 名一律归一化为小写后匹配（Windows ini 常见大小写混写）；
* 旧版 ``config.ini``（``[Paths]/[Defaults]/[Conversion]`` + ``default_*_to_format``
  + ``overwrite`` + ``pdf_chunk_size``）会被自动迁移，并在警告列表里说明迁移结果；
* 非法值不抛异常，回退默认并计入 :attr:`ConfigManager.warnings`。
"""

from __future__ import annotations

import configparser
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from docmorph.settings.paths import default_config_path
from docmorph.settings.schema import (
    CONFIG_VERSION,
    DEFAULTS,
    Settings,
    build_settings,
    coerce_changes,
    env_overrides,
    render_default_ini,
    render_settings_ini,
)

_LEGACY_TARGET_KEY = "default_"
_LEGACY_PROMPT = "已从旧版配置迁移"


class ConfigManager:
    """加载、校验并持有 :class:`Settings`。"""

    def __init__(self, path: os.PathLike | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()
        self.warnings: list[str] = []
        self._raw: dict[str, dict[str, str]] = {}
        self._settings: Settings | None = None
        self._load_file()

    # ------------------------------------------------------------------ 读
    @classmethod
    def load(cls, path: os.PathLike | None = None) -> ConfigManager:
        """读取配置；文件不存在时按默认值工作（不写盘）。"""
        return cls(path)

    @classmethod
    def load_or_create(cls, path: os.PathLike | None = None) -> ConfigManager:
        """读取配置；文件不存在时生成模板（首次运行场景）。"""
        manager = cls(path)
        if not manager.path.exists():
            manager.ensure_file()
        return manager

    def _load_file(self) -> None:
        if not self.path.exists():
            return
        parser = configparser.ConfigParser()
        try:
            with self.path.open("r", encoding="utf-8-sig") as handle:
                parser.read_file(handle)
        except (UnicodeDecodeError, configparser.Error) as exc:
            try:
                parser = configparser.ConfigParser()
                with self.path.open("r", encoding="latin-1") as handle:
                    parser.read_file(handle)
                self.warnings.append(f"配置文件 {self.path} 不是 UTF-8 编码，已按 latin-1 读取")
            except (OSError, configparser.Error, UnicodeDecodeError):
                self.warnings.append(f"配置文件 {self.path} 无法解析（{exc}），已全部使用默认值")
                return
        except OSError as exc:
            self.warnings.append(f"配置文件 {self.path} 读取失败（{exc}），已全部使用默认值")
            return

        raw: dict[str, dict[str, str]] = {}
        for section in parser.sections():
            raw[section.strip().lower()] = {
                key.strip().lower(): value.strip() for key, value in parser.items(section)
            }
        self._raw = self._migrate(raw)

    def _migrate(self, raw: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        """把旧版结构/键名映射到新 schema。"""
        migrated: dict[str, dict[str, str]] = {section: dict(values) for section, values in raw.items()}
        notes: list[str] = []

        defaults = migrated.setdefault("defaults", {})
        conversion = migrated.setdefault("conversion", {})
        paths = migrated.setdefault("paths", {})

        # default_docx_to_format -> target_docx
        for key, value in list(defaults.items()):
            if key == "default_general_to_format":
                defaults.setdefault("default_target", value)
                defaults.pop(key, None)
                notes.append("default_general_to_format → default_target")
            elif key.startswith(_LEGACY_TARGET_KEY) and key.endswith("_to_format"):
                source = key[len(_LEGACY_TARGET_KEY) : -len("_to_format")]
                defaults.setdefault(f"target_{source}", value)
                defaults.pop(key, None)
                notes.append(f"default_{source}_to_format → target_{source}")

        # overwrite(bool) -> conflict_policy
        if "overwrite" in conversion:
            legacy = conversion.pop("overwrite").strip().lower()
            if "conflict_policy" not in conversion:
                conversion["conflict_policy"] = "overwrite" if legacy in {"1", "true", "yes", "on"} else "skip"
                notes.append(f"overwrite={legacy} → conflict_policy={conversion['conflict_policy']}")
        if "overwrite_output" in conversion:
            conversion.pop("overwrite_output", None)

        # pdf_chunk_size：新架构按页流式处理，不再需要
        if "pdf_chunk_size" in conversion:
            conversion.pop("pdf_chunk_size")
            notes.append("pdf_chunk_size 已废弃（新引擎按页流式处理）")

        # default_pdf_engine -> pdf_backend_preference
        if "default_pdf_engine" in defaults:
            engine = defaults.pop("default_pdf_engine").strip().lower()
            if "pdf_backend_preference" not in conversion:
                mapping = {
                    "weasyprint": "weasyprint",
                    "word": "word",
                    "wps": "wps",
                    "libreoffice": "libreoffice",
                    "soffice": "libreoffice",
                }
                conversion["pdf_backend_preference"] = mapping.get(engine, "auto")
                notes.append(
                    f"default_pdf_engine={engine} → pdf_backend_preference="
                    f"{conversion['pdf_backend_preference']}"
                )

        # 旧 [Paths] 里的 log_directory 已在新 schema 中
        for legacy_key in ("input_dir", "output_dir", "log_dir"):
            if legacy_key in paths:
                new_key = {"input_dir": "input_directory", "output_dir": "output_directory", "log_dir": "log_directory"}[legacy_key]
                paths.setdefault(new_key, paths.pop(legacy_key))
                notes.append(f"{legacy_key} → {new_key}")

        if notes:
            self.warnings.append(f"{_LEGACY_PROMPT}：" + "；".join(notes))
        return migrated

    # ------------------------------------------------------------------ 取值
    def settings(
        self,
        overrides: Mapping[str, Any] | None = None,
        use_env: bool = True,
    ) -> Settings:
        """按优先级合并出最终的 :class:`Settings`。"""
        merged: dict[str, dict[str, str]] = {section: dict(values) for section, values in DEFAULTS.items()}
        for section, values in self._raw.items():
            merged.setdefault(section, {}).update(values)
        if use_env:
            for section, values in env_overrides().items():
                merged.setdefault(section, {}).update(values)
        if overrides:
            for key, value in overrides.items():
                if value is None:
                    continue
                section, _, name = key.partition(".")
                if not name:
                    continue
                merged.setdefault(section, {})[name] = str(value)

        settings = build_settings(merged, self.warnings)
        self._settings = settings
        return settings

    def get(self, section: str, key: str, fallback: str = "") -> str:
        """读取原始字符串值（未做类型校验），主要用于兼容旧调用点。"""
        lowered = section.strip().lower()
        return self._raw.get(lowered, {}).get(key.strip().lower(), fallback)

    # ------------------------------------------------------------------ 写
    def ensure_file(self, overwrite: bool = False) -> bool:
        """生成默认配置文件；已存在且 ``overwrite=False`` 时跳过。"""
        if self.path.exists() and not overwrite:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(render_default_ini(), encoding="utf-8")
        except OSError as exc:
            self.warnings.append(f"无法写入配置文件 {self.path}：{exc}")
            return False
        return True

    def save(self, settings: Settings) -> bool:
        """把设置写回配置文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(render_settings_ini(settings), encoding="utf-8")
        return True

    def apply_changes(self, changes: Mapping[str, Any]) -> Settings:
        """校验并应用一组设置修改（供界面/命令行使用）。"""
        current = self.settings()
        updated = current.with_overrides(**coerce_changes(dict(changes)))
        self._raw = _settings_to_raw(updated)
        self.save(updated)
        self._settings = updated
        return updated

    def describe(self) -> dict[str, Any]:
        """给 ``docmorph config`` 用的可读快照。"""
        settings = self.settings()
        return {
            "config_path": str(self.path),
            "config_exists": self.path.exists(),
            "config_version": CONFIG_VERSION,
            "settings": settings.as_dict(),
            "warnings": list(self.warnings),
        }


def ensure_user_config() -> ConfigManager:
    """首次运行时创建用户配置文件。"""
    manager = ConfigManager.load_or_create()
    return manager


def iter_default_sections() -> Iterable[str]:
    return DEFAULTS.keys()


def _settings_to_raw(settings: Settings) -> dict[str, dict[str, str]]:
    """把 :class:`Settings` 转回 raw 字典，保证后续 settings() 结果一致。"""
    return {
        "paths": {
            "input_directory": str(settings.input_directory),
            "output_directory": str(settings.output_directory),
            "log_directory": str(settings.log_directory),
            "temp_directory": "" if str(settings.temp_directory) == "." else str(settings.temp_directory),
        },
        "conversion": {
            "conflict_policy": settings.conflict_policy,
            "pdf_backend_preference": settings.pdf_backend_preference,
            "max_workers": str(settings.max_workers),
            "office_timeout_seconds": str(settings.office_timeout_seconds),
            "keep_structure": str(settings.keep_structure).lower(),
            "xlsx_csv_mode": settings.xlsx_csv_mode,
            "extract_media": str(settings.extract_media).lower(),
        },
        "defaults": {"default_target": settings.default_target, **settings.default_targets},
    }
