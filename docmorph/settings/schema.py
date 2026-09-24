"""配置 schema：默认值、类型、取值约束的唯一声明处。

新增一个配置项时**只改这里**（外加 :class:`Settings` 字段），
``config.example.ini`` 由本文件自动生成，避免"文档与代码两处维护"。
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from docmorph.formats import Format, parse_format
from docmorph.settings.paths import (
    default_config_path,
    default_input_dir,
    default_log_dir,
    default_output_dir,
)

CONFIG_VERSION = 2


@dataclass(frozen=True)
class Settings:
    """解析后的运行时配置。"""

    # [paths]
    input_directory: Path
    output_directory: Path
    log_directory: Path
    #: None = 未指定专用临时目录（使用 <程序目录>\runtime\temp）。
    #: 禁止把空字符串解析成 Path(".")，否则中间文件会依赖当前工作目录。
    temp_directory: Path | None
    # [conversion]
    conflict_policy: str
    pdf_backend_preference: str
    max_workers: int
    office_timeout_seconds: int
    keep_structure: bool
    xlsx_csv_mode: str
    extract_media: bool
    temp_retention_hours: int
    # [defaults]
    default_targets: dict[str, str] = field(default_factory=dict)
    default_target: str = "pdf"

    def default_target_for(self, source: Format | str) -> Format:
        """某源格式的默认目标格式。"""
        source_format = parse_format(source)
        key = source_format.value if source_format else str(source).lower()
        candidate = self.default_targets.get(key, self.default_target)
        return parse_format(candidate) or Format.PDF

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("input_directory", "output_directory", "log_directory"):
            data[key] = str(data[key])
        data["temp_directory"] = "" if self.temp_directory is None else str(self.temp_directory)
        return data

    def with_overrides(self, **changes: Any) -> Settings:
        return replace(self, **changes)


# section -> key -> 默认值（字符串形式，便于写 ini）
DEFAULTS: dict[str, dict[str, str]] = {
    "paths": {
        # 路径留空 = 使用内置默认（runtime/*、用户文档下的 DocMorph\input|output）。
        # 让 config.ini 只记录"用户显式改过的值"：这样把整个程序目录拷到另一台机器后，
        # 默认路径会按新机器的程序目录/用户文档重新解析，不会带着旧机器的绝对路径。
        "input_directory": "",
        "output_directory": "",
        "log_directory": "",
        "temp_directory": "",
    },
    "conversion": {
        "conflict_policy": "rename",
        "pdf_backend_preference": "auto",
        "max_workers": "4",
        "office_timeout_seconds": "300",
        "keep_structure": "true",
        "xlsx_csv_mode": "sheets",
        "extract_media": "true",
        "temp_retention_hours": "24",
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

CONFLICT_POLICIES = ("rename", "overwrite", "skip")
PDF_BACKEND_PREFERENCES = ("auto", "word", "wps", "libreoffice", "weasyprint")
XLSX_CSV_MODES = ("sheets", "merged", "first")


class ConfigValueError(ValueError):
    """某个配置值非法（附带键名，便于提示用户）。"""

    def __init__(self, section: str, key: str, value: str, expected: str) -> None:
        super().__init__(f"[{section}] {key} = {value!r} 非法，应为{expected}，已回退默认值")
        self.section = section
        self.key = key
        self.value = value


def parse_bool(section: str, key: str, value: str) -> bool:
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ConfigValueError(section, key, value, "true/false")


def parse_int(section: str, key: str, value: str, minimum: int = 1, maximum: int = 64) -> int:
    try:
        number = int(value.strip())
    except (TypeError, ValueError):
        raise ConfigValueError(section, key, value, "整数") from None
    if not minimum <= number <= maximum:
        raise ConfigValueError(section, key, value, f"{minimum}~{maximum} 之间的整数")
    return number


def parse_choice(section: str, key: str, value: str, choices: tuple[str, ...]) -> str:
    text = value.strip().lower()
    if text not in choices:
        raise ConfigValueError(section, key, value, " / ".join(choices))
    return text


def build_settings(
    raw: dict[str, dict[str, str]],
    warnings: list[str],
) -> Settings:
    """把 ``section -> key -> value`` 的字符串字典转成强类型 :class:`Settings`。

    取值非法时**不抛异常**：记录警告并回退默认值（桌面程序不应因为一个错字无法启动）。
    """

    def get(section: str, key: str) -> str:
        return raw.get(section, {}).get(key, DEFAULTS[section][key])

    def safe(label: str, parser, default, *args):
        section, key = label.split(".")
        try:
            return parser(section, key, get(section, key), *args)
        except ConfigValueError as exc:
            warnings.append(str(exc))
            return parser(section, key, DEFAULTS[section][key], *args)

    def path_or_default(section: str, key: str, default: Path) -> Path:
        """路径取值：空 / ``.`` = 内置默认；支持 ``%USERPROFILE%`` 风格环境变量。

        相对路径一律解析为绝对路径（与 :func:`temp_root` 一致），
        避免被 Word 等 COM 组件按 system32 解析。
        """
        text = os.path.expandvars(get(section, key).strip())
        if not text or text == ".":
            return default
        path = Path(text).expanduser()
        return path if path.is_absolute() else path.resolve()

    temp_raw = os.path.expandvars(get("paths", "temp_directory").strip())
    if not temp_raw or temp_raw == ".":
        temp_directory: Path | None = None
    else:
        temp_path = Path(temp_raw).expanduser()
        temp_directory = temp_path if temp_path.is_absolute() else temp_path.resolve()
    settings = Settings(
        input_directory=path_or_default("paths", "input_directory", default_input_dir()),
        output_directory=path_or_default("paths", "output_directory", default_output_dir()),
        log_directory=path_or_default("paths", "log_directory", default_log_dir()),
        temp_directory=temp_directory,
        conflict_policy=safe("conversion.conflict_policy", parse_choice, None, CONFLICT_POLICIES),
        pdf_backend_preference=safe(
            "conversion.pdf_backend_preference", parse_choice, None, PDF_BACKEND_PREFERENCES
        ),
        max_workers=safe("conversion.max_workers", parse_int, None, 1, 32),
        office_timeout_seconds=safe(
            "conversion.office_timeout_seconds", parse_int, None, 10, 7200
        ),
        keep_structure=safe("conversion.keep_structure", parse_bool, None),
        xlsx_csv_mode=safe("conversion.xlsx_csv_mode", parse_choice, None, XLSX_CSV_MODES),
        extract_media=safe("conversion.extract_media", parse_bool, None),
        temp_retention_hours=safe("conversion.temp_retention_hours", parse_int, None, 0, 720),
        default_targets={
            key.removeprefix("target_"): get("defaults", key)
            for key in DEFAULTS["defaults"]
            if key.startswith("target_")
        },
        default_target=get("defaults", "default_target"),
    )
    return settings


def render_default_ini() -> str:
    """按当前 DEFAULTS 生成带注释的配置文件内容。"""
    lines = [
        "# DocMorph 配置文件（自动生成，可直接编辑）",
        "# 修改后重启程序生效；删除本文件将恢复全部默认值。",
        "",
        "[meta]",
        f"version = {CONFIG_VERSION}",
        "",
        "[paths]",
        "# 输入 / 输出目录：留空 = 默认（用户文档下的 DocMorph\\input|output）",
        "# 注意：不要把输入输出目录设为源代码目录，避免污染项目",
        "input_directory =",
        "output_directory =",
        "# 日志目录：留空 = 程序目录下的 runtime\\logs",
        "log_directory =",
        "# 临时工作区：留空 = 程序目录下的 runtime\\temp\\<会话 id>",
        "temp_directory =",
        "",
        "[conversion]",
        "# 目标文件已存在时：rename（自动改名，默认）/ overwrite / skip",
        f"conflict_policy = {DEFAULTS['conversion']['conflict_policy']}",
        "# PDF 引擎偏好：auto / word / wps / libreoffice / weasyprint",
        f"pdf_backend_preference = {DEFAULTS['conversion']['pdf_backend_preference']}",
        "# 批量转换并发数（Office 后端始终串行）",
        f"max_workers = {DEFAULTS['conversion']['max_workers']}",
        "# 单个 Office 转换的最长等待秒数",
        f"office_timeout_seconds = {DEFAULTS['conversion']['office_timeout_seconds']}",
        "# 批量转换是否保留输入目录结构",
        f"keep_structure = {DEFAULTS['conversion']['keep_structure']}",
        "# xlsx 转 csv 模式：sheets（每表一个文件）/ merged / first",
        f"xlsx_csv_mode = {DEFAULTS['conversion']['xlsx_csv_mode']}",
        "# 转 Markdown 时是否把图片抽取到同名 _media 目录",
        f"extract_media = {DEFAULTS['conversion']['extract_media']}",
        "# 启动时清理多少小时之前的遗留临时目录（0 表示不清理）",
        f"temp_retention_hours = {DEFAULTS['conversion']['temp_retention_hours']}",
        "",
        "[defaults]",
        "# 各源格式的默认目标格式",
    ]
    for key, value in DEFAULTS["defaults"].items():
        lines.append(f"{key} = {value}")
    lines.append("")
    return "\n".join(lines)


def default_config_file() -> Path:
    return default_config_path()


def env_overrides(environ: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
    """从 ``DOCMORPH_<SECTION>_<KEY>`` 环境变量读取覆盖值。"""
    env = environ if environ is not None else os.environ
    result: dict[str, dict[str, str]] = {}
    for name, value in env.items():
        if not name.startswith("DOCMORPH_"):
            continue
        rest = name[len("DOCMORPH_") :].lower()
        for section, keys in DEFAULTS.items():
            for key in keys:
                if rest == f"{section}_{key}":
                    result.setdefault(section, {})[key] = value
    return result


def coerce_changes(changes: dict[str, Any]) -> dict[str, Any]:
    """把来自界面/命令行的"松散"取值转成 :class:`Settings` 要求的类型。

    取值不合法时抛 :class:`ConfigValueError`，由调用方翻译成用户提示。
    """
    path_defaults = {
        "input_directory": default_input_dir,
        "output_directory": default_output_dir,
        "log_directory": default_log_dir,
    }
    result: dict[str, Any] = {}
    for key, value in changes.items():
        if value is None:
            continue
        if key == "temp_directory":
            text = str(value).strip()
            if not text or text == ".":
                result[key] = None
            else:
                path = Path(text).expanduser()
                result[key] = path if path.is_absolute() else path.resolve()
        elif key in path_defaults:
            text = str(value).strip()
            if not text or text == ".":
                # 留空 = 恢复内置默认（保证 config.ini 可随程序目录整体拷贝）
                result[key] = path_defaults[key]()
            else:
                path = Path(text).expanduser()
                result[key] = path if path.is_absolute() else path.resolve()
        elif key == "conflict_policy":
            result[key] = parse_choice("conversion", key, str(value), CONFLICT_POLICIES)
        elif key == "pdf_backend_preference":
            result[key] = parse_choice("conversion", key, str(value), PDF_BACKEND_PREFERENCES)
        elif key == "xlsx_csv_mode":
            result[key] = parse_choice("conversion", key, str(value), XLSX_CSV_MODES)
        elif key == "max_workers":
            result[key] = parse_int("conversion", key, str(value), 1, 32)
        elif key == "office_timeout_seconds":
            result[key] = parse_int("conversion", key, str(value), 10, 7200)
        elif key == "temp_retention_hours":
            result[key] = parse_int("conversion", key, str(value), 0, 720)
        elif key in {"keep_structure", "extract_media"}:
            result[key] = value if isinstance(value, bool) else parse_bool("conversion", key, str(value))
        elif key == "default_target":
            if parse_format(value) is None:
                raise ConfigValueError("defaults", key, str(value), "受支持的格式名")
            result[key] = str(value)
        else:
            raise ConfigValueError("", key, str(value), "已知的配置项")
    return result


def _same_path(value: Path, default: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(value))) == os.path.normcase(
        os.path.normpath(str(default))
    )


def _path_setting(value: Path, default: Path) -> str:
    """与内置默认一致时写空串：config.ini 拷贝到其它机器后按该机器的默认重新解析。"""
    return "" if _same_path(value, default) else str(value)


def render_settings_ini(settings: Settings) -> str:
    """把当前设置写回 ini（保留文件头注释，值来自实际设置）。"""
    targets = "\n".join(
        f"target_{key} = {value}" for key, value in settings.default_targets.items()
    )
    return (
        "# DocMorph 配置文件\n"
        "# 由程序写入；删除本文件将恢复全部默认值。\n"
        "\n"
        "[meta]\n"
        f"version = {CONFIG_VERSION}\n"
        "\n"
        "[paths]\n"
        f"input_directory = {_path_setting(settings.input_directory, default_input_dir())}\n"
        f"output_directory = {_path_setting(settings.output_directory, default_output_dir())}\n"
        f"log_directory = {_path_setting(settings.log_directory, default_log_dir())}\n"
        f"temp_directory = {settings.temp_directory if settings.temp_directory is not None else ''}\n"
        "\n"
        "[conversion]\n"
        f"conflict_policy = {settings.conflict_policy}\n"
        f"pdf_backend_preference = {settings.pdf_backend_preference}\n"
        f"max_workers = {settings.max_workers}\n"
        f"office_timeout_seconds = {settings.office_timeout_seconds}\n"
        f"keep_structure = {str(settings.keep_structure).lower()}\n"
        f"xlsx_csv_mode = {settings.xlsx_csv_mode}\n"
        f"extract_media = {str(settings.extract_media).lower()}\n"
        f"temp_retention_hours = {settings.temp_retention_hours}\n"
        "\n"
        "[defaults]\n"
        f"default_target = {settings.default_target}\n"
        f"{targets}\n"
    )
