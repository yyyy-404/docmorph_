"""分层配置系统（默认值 < 用户配置 < 环境变量 < 运行时覆盖）。"""

from docmorph.settings.manager import ConfigManager, ensure_user_config
from docmorph.settings.paths import (
    APP_NAME,
    TempWorkspace,
    app_config_dir,
    app_data_dir,
    default_config_path,
    default_input_dir,
    default_log_dir,
    default_output_dir,
)
from docmorph.settings.schema import (
    CONFIG_VERSION,
    CONFLICT_POLICIES,
    DEFAULTS,
    PDF_BACKEND_PREFERENCES,
    XLSX_CSV_MODES,
    Settings,
    render_default_ini,
)

__all__ = [
    "APP_NAME",
    "CONFIG_VERSION",
    "CONFLICT_POLICIES",
    "DEFAULTS",
    "PDF_BACKEND_PREFERENCES",
    "XLSX_CSV_MODES",
    "ConfigManager",
    "Settings",
    "TempWorkspace",
    "app_config_dir",
    "app_data_dir",
    "default_config_path",
    "default_input_dir",
    "default_log_dir",
    "default_output_dir",
    "ensure_user_config",
    "render_default_ini",
]
