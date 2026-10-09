"""Bundled resources and persistent paths for source and executable launches."""
import os
from pathlib import Path
import re
import sys


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


def resource_root(project_root=None):
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]


def workspace_root():
    if not is_frozen():
        return resource_root()
    # Build/smoke tooling can isolate its cache without depending on developer
    # extraction caches. Normal app launches use the user's local data folder.
    override = os.environ.get('FFTIC_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))
    return local/'FFTIC Randomizer'


def _registry_value(key, name):
    if os.name != 'nt':
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            return os.path.expandvars(winreg.QueryValueEx(handle, name)[0])
    except OSError:
        return None


def default_output_dir(project_root):
    if not is_frozen():
        return Path(project_root)/'outputs'
    documents = _registry_value(r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders', 'Personal')
    return (Path(documents) if documents else Path.home()/'Documents')/'FFTIC Randomizer/Seeds'


def default_game_dir(project_root):
    if not is_frozen():
        return Path(project_root).parent
    # A portable exe can be anywhere. First check nearby game directories,
    # then Steam's registered libraries rather than assuming a drive letter.
    executable = Path(sys.executable).resolve()
    candidates = list(executable.parents)[:5]
    steam = _registry_value(r'Software\Valve\Steam', 'SteamPath')
    steam_roots = [Path(steam)] if steam else []
    program_files = os.environ.get('PROGRAMFILES(X86)')
    if program_files:
        steam_roots.append(Path(program_files)/'Steam')
    for folder in tuple(steam_roots):
        libraries = folder/'steamapps/libraryfolders.vdf'
        if libraries.is_file():
            try:
                text = libraries.read_text(encoding='utf-8')
                steam_roots.extend(Path(match.replace('\\\\', '\\'))
                                   for match in re.findall(r'"path"\s+"([^"]+)"', text))
            except OSError:
                pass
    candidates.extend(folder/'steamapps/common/FINAL FANTASY TACTICS - The Ivalice Chronicles'
                      for folder in steam_roots)
    for folder in candidates:
        if (folder/'FFT_enhanced.exe').is_file():
            return folder
    return executable.parent


def converter_environment():
    environment = os.environ.copy()
    dotnet = resource_root()/'vendor/dotnet'
    if (dotnet/'dotnet.exe').is_file():
        environment.update(DOTNET_ROOT=str(dotnet), DOTNET_ROOT_X64=str(dotnet),
                           DOTNET_MULTILEVEL_LOOKUP='0')
        environment['PATH'] = str(dotnet)+os.pathsep+environment.get('PATH', '')
    if is_frozen():
        environment['DOTNET_BUNDLE_EXTRACT_BASE_DIR'] = str(workspace_root()/'converter-cache')
    return environment
