"""Linux launch paths and converter subprocess contracts, without game inputs."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fftic import gui, preview, runtime


GAME_FOLDER = 'FINAL FANTASY TACTICS - The Ivalice Chronicles'


class LinuxRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.home = self.root/'home'
        self.home.mkdir()
        self.bundle = self.root/'bundle'
        self.bundle.mkdir()
        self.launcher = self.root/'portable/FFTIC Randomizer'
        self.launcher.parent.mkdir()
        for replacement in (
                patch.object(Path, 'home', return_value=self.home),
                patch.object(runtime, 'is_linux', return_value=True),
                patch.object(preview, 'is_linux', return_value=True),
                patch.object(gui, 'is_linux', return_value=True),
                patch.object(runtime.sys, 'executable', str(self.launcher)),
                patch.object(runtime, 'resource_root', return_value=self.bundle),
                patch.dict(os.environ, {}, clear=True)):
            replacement.start()
            self.addCleanup(replacement.stop)

    def game_at(self, library):
        game = library/'steamapps/common'/GAME_FOLDER
        game.mkdir(parents=True)
        (game/'FFT_enhanced.exe').write_bytes(b'verified by generation separately')
        return game

    def test_frozen_cache_is_xdg_and_source_paths_remain_local(self):
        custom = self.root/'custom cache'
        with patch.object(runtime, 'is_frozen', return_value=True):
            self.assertEqual(runtime.workspace_root(), self.home/'.cache/fftic-randomizer')
            with patch.dict(os.environ, {'XDG_CACHE_HOME': str(custom)}):
                self.assertEqual(runtime.workspace_root(), custom/'fftic-randomizer')
            with patch.dict(os.environ, {'XDG_CACHE_HOME': 'relative-cache'}):
                self.assertEqual(runtime.workspace_root(), self.home/'.cache/fftic-randomizer')
            with patch.dict(os.environ, {'FFTIC_DATA_DIR': str(custom)}):
                self.assertEqual(runtime.workspace_root(), custom.resolve())
        with patch.object(runtime, 'is_frozen', return_value=False):
            self.assertEqual(runtime.workspace_root(), self.bundle)
            self.assertEqual(runtime.default_output_dir(self.root), self.root/'outputs')
            self.assertEqual(runtime.default_game_dir(self.root), self.root.parent)

    def test_documents_setting_uses_localized_folder_without_executing_shell(self):
        config = self.root/'configuration'
        config.mkdir()
        settings = config/'user-dirs.dirs'
        settings.write_text('XDG_DOCUMENTS_DIR="$HOME/Dokumente mit Leerzeichen"\n', encoding='utf-8')
        with patch.object(runtime, 'is_frozen', return_value=True), patch.dict(os.environ, {'XDG_CONFIG_HOME': str(config)}):
            self.assertEqual(runtime.default_output_dir(self.root),
                             self.home/'Dokumente mit Leerzeichen/FFTIC Randomizer/Seeds')
            settings.write_text('XDG_DOCUMENTS_DIR="relative/path"\n', encoding='utf-8')
            self.assertEqual(runtime.default_output_dir(self.root), self.home/'Documents/FFTIC Randomizer/Seeds')
            # Disabled user-dirs entries deliberately point directly at HOME.
            settings.write_text('XDG_DOCUMENTS_DIR="${HOME}"\n', encoding='utf-8')
            self.assertEqual(runtime.default_output_dir(self.root), self.home/'FFTIC Randomizer/Seeds')

    def test_native_and_flatpak_steam_libraries_find_external_game_install(self):
        for index, relative in enumerate(('.local/share/Steam', '.steam/root',
                                         '.var/app/com.valvesoftware.Steam/.local/share/Steam')):
            with self.subTest(steam=relative):
                steam = self.home/relative
                libraries = steam/'steamapps/libraryfolders.vdf'
                libraries.parent.mkdir(parents=True, exist_ok=True)
                external = self.root/f'card {index}'
                expected = self.game_at(external)
                escaped = str(external).replace('\\', '\\\\')
                libraries.write_text('"libraryfolders"\n{\n"1"\n{\n"path" "'+escaped+'"\n}\n}\n', encoding='utf-8')
                with patch.object(runtime, 'is_frozen', return_value=True):
                    self.assertEqual(runtime.default_game_dir(self.root), expected)
                libraries.unlink()

    def test_appimage_location_is_used_before_steam_and_windows_default_is_preserved(self):
        portable_game = self.root/'beside-appimage'
        portable_game.mkdir()
        (portable_game/'FFT_enhanced.exe').write_bytes(b'game')
        appimage = portable_game/'FFTIC Randomizer.AppImage'
        with patch.object(runtime, 'is_frozen', return_value=True), patch.dict(os.environ, {'APPIMAGE': str(appimage)}):
            self.assertEqual(runtime.default_game_dir(self.root), portable_game)
        with patch.object(runtime, 'is_frozen', return_value=True), patch.object(runtime, 'is_linux', return_value=False), patch.object(runtime, '_registry_value', return_value=None):
            self.assertEqual(runtime.workspace_root(), self.home/'AppData/Local/FFTIC Randomizer')
            self.assertEqual(runtime.default_output_dir(self.root), self.home/'Documents/FFTIC Randomizer/Seeds')
            self.assertEqual(runtime.default_game_dir(self.root), self.launcher.parent)

    def test_native_converter_is_selected_and_frozen_override_is_ignored(self):
        folder = self.bundle/'vendor/FF16Tools-1.13.3/native'
        folder.mkdir(parents=True)
        native, windows = folder/'FF16Tools.CLI', folder/'FF16Tools.CLI.exe'
        native.write_bytes(b'ELF')
        windows.write_bytes(b'MZ')
        configured = self.root/'custom-converter'
        configured.write_bytes(b'custom')
        with patch.object(preview, 'resource_root', return_value=self.bundle), patch.dict(os.environ, {'FFTIC_FF16TOOLS': str(configured)}):
            with patch.object(preview, 'is_frozen', return_value=True):
                self.assertEqual(preview.locate_cli(self.root), native)
                with patch.object(preview, 'is_linux', return_value=False):
                    self.assertEqual(preview.locate_cli(self.root), windows)
            with patch.object(preview, 'is_frozen', return_value=False):
                self.assertEqual(preview.locate_cli(self.root), configured.resolve())
        native.unlink()
        with patch.object(preview, 'resource_root', return_value=self.bundle), patch.object(preview, 'is_frozen', return_value=True):
            with self.assertRaisesRegex(ValueError, 'FF16Tools.CLI'):
                preview.locate_cli(self.root)

    def test_dotnet_environment_only_adds_matching_bundled_host(self):
        dotnet = self.bundle/'vendor/dotnet'
        dotnet.mkdir(parents=True)
        (dotnet/'dotnet.exe').write_bytes(b'Windows host')
        with patch.object(runtime, 'is_frozen', return_value=True):
            standalone = runtime.converter_environment()
            self.assertNotIn('DOTNET_ROOT', standalone)
            self.assertEqual(standalone['DOTNET_BUNDLE_EXTRACT_BASE_DIR'],
                             str(self.home/'.cache/fftic-randomizer/converter-cache'))
            (dotnet/'dotnet').write_bytes(b'Linux host')
            shared = runtime.converter_environment()
            self.assertEqual(shared['DOTNET_ROOT'], str(dotnet))
            self.assertEqual(shared['DOTNET_ROOT_X64'], str(dotnet))
            self.assertEqual(shared['DOTNET_MULTILEVEL_LOOKUP'], '0')
            self.assertEqual(shared['PATH'].split(os.pathsep)[0], str(dotnet))

    def test_open_folder_uses_detached_argument_list_for_paths_with_spaces(self):
        output = self.root/'Seed outputs; still a folder'
        output.mkdir()
        with patch.object(gui.subprocess, 'Popen') as launch:
            gui._open_folder(output)
        arguments, options = launch.call_args
        self.assertEqual(arguments, (['xdg-open', str(output.resolve())],))
        self.assertTrue(options['start_new_session'])
        self.assertTrue(options['close_fds'])
        self.assertNotIn('shell', options)

    def test_system_file_manager_does_not_inherit_frozen_library_overrides(self):
        with patch.object(runtime, 'is_frozen', return_value=True), patch.dict(os.environ, {'LD_LIBRARY_PATH': '/bundle/lib', 'LD_LIBRARY_PATH_ORIG': '/user/lib'}):
            with patch.object(gui.subprocess, 'Popen') as launch:
                gui._open_folder(self.root)
            self.assertEqual(launch.call_args.kwargs['env']['LD_LIBRARY_PATH'], '/user/lib')
            self.assertEqual(os.environ['LD_LIBRARY_PATH'], '/bundle/lib')
        with patch.object(runtime, 'is_frozen', return_value=True), patch.dict(os.environ, {'LD_LIBRARY_PATH': '/bundle/lib'}):
            self.assertNotIn('LD_LIBRARY_PATH', runtime.external_application_environment())

    def test_converter_runner_captures_real_child_output_and_rejects_failure(self):
        # Real subprocesses exercise cwd/env/Unicode logging on either OS. Use
        # the running interpreter, not the mocked frozen launcher path.
        executable = Path(sys._base_executable)
        log = self.root/'converter.log'
        preview.run_cli(executable, ['-c', 'import sys; print("success"); print("detail", file=sys.stderr)'], log)
        self.assertIn('success', log.read_text(encoding='utf-8'))
        self.assertIn('detail', log.read_text(encoding='utf-8'))
        with self.assertRaisesRegex(ValueError, 'conversion failed'):
            preview.run_cli(executable, ['-c', 'import sys; print("failed", file=sys.stderr); sys.exit(2)'], log)
        self.assertIn('failed', log.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
