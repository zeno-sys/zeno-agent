from pathlib import Path
import os

os.environ["ZENO_HOME"] = (Path.cwd() / "data").absolute().as_posix()

def get_zeno_home() -> Path:
    """Return the Zeno home directory (default: ~/.zeno)."""
    val = os.environ.get("ZENO_HOME", "").strip()
    return Path(val) if val else Path.home() / ".zeno"

def display_zeno_home() -> str:
    """返回zeno的显示路径
    """
    home = get_zeno_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)

def get_config_path() -> Path:
    """Return the path to ``config.yaml`` under HERMES_HOME.

    Replaces the ``get_hermes_home() / "config.yaml"`` pattern repeated
    in 7+ files (skill_utils.py, hermes_logging.py, hermes_time.py, etc.).
    """
    return get_zeno_home() / "config.yaml"


def get_skills_dir() -> Path:
    """Return the path to the skills directory under HERMES_HOME."""
    return get_workspace_path() / "skills"

def get_workspace_path()->Path:
    return Path.cwd()

def get_mcp_config_path()->Path:
    return Path("data/config/mcp.yaml")


_wsl_detected: bool | None = None

def is_wsl() -> bool:
    """Return True when running inside WSL (Windows Subsystem for Linux).

    Checks ``/proc/version`` for the ``microsoft`` marker that both WSL1
    and WSL2 inject.  Result is cached for the process lifetime.
    Import-safe — no heavy deps.
    """
    global _wsl_detected
    if _wsl_detected is not None:
        return _wsl_detected
    try:
        with open("/proc/version", "r") as f:
            _wsl_detected = "microsoft" in f.read().lower()
    except Exception:
        _wsl_detected = False
    return _wsl_detected


if __name__ == "__main__":
    print(get_zeno_home().absolute())
    print(display_zeno_home())
    print(get_workspace_path().absolute())
    print(get_mcp_config_path().absolute())
    print(get_skills_dir().absolute())
    import yaml
    config = yaml.load(get_mcp_config_path().read_text(), Loader=yaml.FullLoader)
    servers = config.get("mcp_servers")
    print(servers)