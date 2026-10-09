"""Read report labels from the user's original English game archive."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from .preview import locate_cli, run_cli


TABLES = {
    'Job': ('Job-en', 'job.en.nxd'),
    'Item': ('Item-en', 'item.en.nxd'),
    'JobCommand': ('JobCommand-en', 'jobcommand.en.nxd'),
}


def _read_names(database):
    names = {}
    with closing(sqlite3.connect(database)) as connection:
        for kind, (table, _) in TABLES.items():
            columns = {row[1]: row[2] for row in connection.execute(
                'PRAGMA table_info("' + table + '")')}
            if columns.get('Key') != 'INTEGER' or columns.get('Name') != 'TEXT':
                raise ValueError('Original report-name table schema changed: ' + table)
            rows = connection.execute('SELECT "Key", "Name" FROM "' + table + '"').fetchall()
            if not rows or any(type(key) is not int or key < 0 for key, _ in rows):
                raise ValueError('Original report-name table has invalid keys: ' + table)
            if len({key for key, _ in rows}) != len(rows):
                raise ValueError('Original report-name table has duplicate keys: ' + table)
            if any(name is not None and not isinstance(name, str) for _, name in rows):
                raise ValueError('Original report-name table has invalid names: ' + table)
            # Undefined slots intentionally have no name. Leave them absent so
            # the report's numeric fallback remains authoritative for those IDs.
            names[kind] = {str(key): name for key, name in rows if name}
            if not names[kind]:
                raise ValueError('Original report-name table has no names: ' + table)
    return names


def prepare_report_names(game_dir, project_root):
    archive = Path(game_dir) / 'data/enhanced/0004.en.pac'
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    cache = Path(project_root) / 'research/report-names' / archive_hash[:16]
    cache.mkdir(parents=True, exist_ok=True)
    database, receipt = cache / 'base.sqlite', cache / 'inputs.json'
    files = ['base.sqlite', *('nxd/' + filename for _, filename in TABLES.values())]
    if receipt.is_file():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if (record.get('archive_sha256') != archive_hash or
                record.get('schema_version') != 1 or
                set(record.get('files_sha256', {})) != set(files)):
            raise ValueError('Original report-name cache receipt changed; re-extract its folder')
        for name in files:
            path = cache / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record['files_sha256'][name]:
                raise ValueError('Original report-name cache changed: ' + name)
        return _read_names(database)

    cli = locate_cli(project_root)
    for _, filename in TABLES.values():
        run_cli(cli, ['unpack', '-i', archive, '-f', 'nxd/' + filename,
                      '-o', cache, '-g', 'fft'], cache / ('extract-' + filename + '.log'))
    if any(not (cache / name).is_file() for name in files[1:]):
        raise ValueError('Report-name extraction did not produce every required table')
    run_cli(cli, ['nxd-to-sqlite', '-i', cache / 'nxd', '-o', database, '-g', 'fft'],
            cache / 'convert.log')
    names = _read_names(database)
    record = dict(schema_version=1, archive_sha256=archive_hash,
                  files_sha256={name: hashlib.sha256((cache / name).read_bytes()).hexdigest()
                                for name in files})
    receipt.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return names
