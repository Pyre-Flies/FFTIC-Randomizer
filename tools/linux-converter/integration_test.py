"""Exercise the published converter with synthetic PAC and NXD/SQLite inputs.

The compressed bytes come from the official CPU reference compressor's fixture
generator. These files contain no original game data and are not release assets.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import zlib


def path_hash(value: str) -> int:
    result = 0x811c9dc5
    for byte in value.encode('ascii'):
        result = ((result * 16777619) ^ byte) & 0xffffffff
    return result


def synthetic_pack(expected: bytes, compressed: bytes, *, shared: bool) -> tuple[bytes, bytes]:
    """Create one unencrypted PACK entry, either specific or in a shared chunk."""
    name = 'fixtures/synthetic.bin'
    header_size = 0x500
    chunk_offset = 0x438 if shared else 0
    name_offset = 0x450 if shared else 0x438
    start = 17 if shared else 0
    payload = expected[start:start + 65537] if shared else expected
    header = bytearray(header_size)
    struct.pack_into('<IIIBBHQ', header, 0, 0x4b434150, header_size, 1,
                     int(shared), 0, int(shared), header_size + len(compressed))
    struct.pack_into('<QQQ', header, 0x118, chunk_offset, name_offset, len(name) + 1)
    struct.pack_into('<IBBHQQQQIIII', header, 0x400, len(compressed), 1,
                     3 if shared else 1, 0, len(payload), start if shared else header_size,
                     chunk_offset, name_offset, path_hash(name), zlib.crc32(payload), 0, 0)
    if shared:
        struct.pack_into('<QIIIHH', header, chunk_offset, header_size,
                         len(compressed), len(expected), 0, 0, 1)
    header[name_offset:name_offset + len(name) + 1] = name.encode('ascii') + b'\0'
    return bytes(header) + compressed, payload


def run_cli(cli: Path, args: list[str], work: Path, name: str) -> None:
    result = subprocess.run([str(cli), *args], cwd=cli.parent,
                            capture_output=True, text=True, errors='replace')
    log = result.stdout + '\n' + result.stderr
    (work / f'{name}.log').write_text(log, encoding='utf-8')
    if result.returncode or '[Error]' in log or 'Failed to unpack' in log:
        raise ValueError(f'Synthetic CLI integration failed: {name}; see its log')


def test_converter(cli: Path, fixtures: Path, work: Path) -> dict:
    cli, fixtures, work = cli.resolve(), fixtures.resolve(), work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    globalization = None
    config = cli.parent / 'FF16Tools.CLI.runtimeconfig.json'
    if config.is_file():
        properties = json.loads(config.read_text(encoding='utf-8'))['runtimeOptions'].get('configProperties', {})
        if properties.get('System.Globalization.AppLocalIcu'):
            if (properties['System.Globalization.AppLocalIcu'] != '72.1.0.3' or
                    properties.get('System.Globalization.Invariant') is not False):
                raise ValueError('Converter globalization configuration differs from the pinned full ICU runtime')
            run_cli(cli, ['--fftic-globalization-probe'], work, 'globalization-probe')
            globalization = json.loads((work / 'globalization-probe.log').read_text(encoding='utf-8').strip().lstrip('\ufeff'))
            if (globalization.get('result') != 'passed' or globalization.get('icu_version') != '72.1.0.3'
                    or globalization.get('invariant_mode') is not False
                    or globalization.get('icu_from_app_directory') is not True
                    or set(globalization.get('culture_checks', [])) != {'fr-FR', 'tr-TR', 'ja-JP', 'zh-CN'}
                    or set(globalization.get('icu_libraries', [])) != {
                        'libicudata.so.72.1.0.3', 'libicuuc.so.72.1.0.3', 'libicui18n.so.72.1.0.3'}):
                raise ValueError('Converter did not verify full globalization using only app-local ICU libraries')
    source = (fixtures / '131089-1.bin').read_bytes()
    compressed = (fixtures / '131089-1.gdeflate').read_bytes()
    for shared in (False, True):
        name = 'shared' if shared else 'specific'
        archive, wanted = synthetic_pack(source, compressed, shared=shared)
        pack = work / f'{name}.pac'
        pack.write_bytes(archive)
        destination = work / name
        extracted = destination / 'fixtures/synthetic.bin'
        if extracted.is_file():
            extracted.unlink()
        run_cli(cli, ['unpack', '-i', str(pack), '-f', 'fixtures/synthetic.bin',
                      '-o', str(destination), '-g', 'fft'], work, name)
        if not extracted.is_file() or extracted.read_bytes() != wanted:
            raise ValueError(f'Synthetic {name} compressed PAC did not extract exact bytes')

    original = work / 'synthetic.sqlite'
    expected = [(1, 0, 'Linux native fixture', 0.5),
                (17, 1, 'UTF-8 fixture: agréable', 1.5),
                (42, 2, '日本語: 月曜日', 2.25),
                (43, 3, '中文: 简体與繁體', -0.5),
                (44, 4, '한국어: 아이발리스', 0.125),
                (45, 5, 'Русский: Ивалис', 16.0),
                (46, 6, 'Emoji: 😀🌕', 3.5),
                (47, 7, 'Combining accent: Cafe\u0301', 0.75)]
    with closing(sqlite3.connect(original)) as database:
        database.execute('DROP TABLE IF EXISTS Brightness')
        database.execute('CREATE TABLE Brightness (Key INTEGER, DLCFlags INTEGER, Comment TEXT, Value REAL)')
        database.execute('CREATE TABLE IF NOT EXISTS _uniontypes (id INTEGER PRIMARY KEY, name TEXT)')
        database.executemany('INSERT INTO Brightness VALUES (?,?,?,?)', expected)
        database.commit()
    tables = work / 'nxd'
    tables.mkdir(exist_ok=True)
    emitted = tables / 'brightness.nxd'
    if emitted.is_file():
        emitted.unlink()
    run_cli(cli, ['sqlite-to-nxd', '-i', str(original), '-t', 'Brightness',
                  '-o', str(tables), '-g', 'fft'], work, 'sqlite-to-nxd')
    if not emitted.is_file():
        raise ValueError('Synthetic NXD table was not emitted')
    rebuilt = work / 'roundtrip.sqlite'
    if rebuilt.is_file():
        rebuilt.unlink()
    run_cli(cli, ['nxd-to-sqlite', '-i', str(tables), '-o', str(rebuilt),
                  '-g', 'fft'], work, 'nxd-to-sqlite')
    with closing(sqlite3.connect(rebuilt)) as database:
        actual = database.execute('SELECT Key,DLCFlags,Comment,Value FROM Brightness ORDER BY Key').fetchall()
    if actual != expected:
        raise ValueError('Synthetic NXD/SQLite roundtrip did not retain exact rows')
    result = dict(specific_compressed_pac='exact bytes matched',
                  shared_compressed_pac='exact bytes matched',
                  nxd_sqlite_roundtrip='eight exact rows including multilingual UTF-8, emoji, combining marks and float cells')
    if globalization is not None:
        result['globalization_probe'] = globalization
    (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    test_converter(args.cli, args.fixtures, args.work)
    print('Published converter: specific/shared compressed PAC extraction and NXD/SQLite roundtrip passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
