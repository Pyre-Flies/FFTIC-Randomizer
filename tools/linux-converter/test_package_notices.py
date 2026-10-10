"""Regression checks for NuGet's distinct signed-content and archive hashes."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import build


class NoticeArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        original_root = build.ROOT
        self.addCleanup(setattr, build, 'ROOT', original_root)
        build.ROOT = self.root
        self.cache = self.root / 'packages/fixture.package/1.0.0'
        self.cache.mkdir(parents=True)
        self.cached_archive = self.cache / 'fixture.package.1.0.0.nupkg'
        with zipfile.ZipFile(self.cached_archive, 'w') as archive:
            archive.writestr('fixture.nuspec', '<package/>')
            archive.writestr('lib/net9.0/fixture.dll', b'synthetic dependency bytes')
            archive.writestr('.signature.p7s', b'synthetic signature bytes')
        self.downloaded = self.root / 'vendor/executable-licenses/nuget/Fixture.Package.1.0.0.nupkg'
        self.downloaded.parent.mkdir(parents=True)
        self.downloaded.write_bytes(self.cached_archive.read_bytes())
        self.raw_hash = self.hash(self.cached_archive.read_bytes())
        # A signed-content hash is intentionally distinct from the whole ZIP.
        self.content_hash = self.hash(b'synthetic unsigned package content')
        (self.cache / 'fixture.package.1.0.0.nupkg.sha512').write_text(self.raw_hash)
        self.metadata = self.cache / '.nupkg.metadata'
        self.metadata.write_text(json.dumps({'contentHash': self.content_hash}))
        self.assets = dict(libraries={'Fixture.Package/1.0.0': dict(
            type='package', path='fixture.package/1.0.0', sha512=self.content_hash)},
            packageFolders={str(self.root / 'packages'): {}})
        self.notice = dict(package='Fixture.Package/1.0.0',
                           dependency_sha512='sha512-' + self.content_hash)

    @staticmethod
    def hash(value):
        return base64.b64encode(hashlib.sha512(value).digest()).decode('ascii')

    def test_signed_content_and_archive_hashes_can_differ(self):
        self.assertNotEqual(self.raw_hash, self.content_hash)
        result = build.verify_notice_archive(self.notice, self.assets)
        self.assertEqual(result['package_archive_sha512'], 'sha512-' + self.raw_hash)
        self.assertEqual(result['restored_content_sha512'], 'sha512-' + self.content_hash)

    def test_official_archive_must_equal_the_restored_archive(self):
        self.downloaded.write_bytes(self.downloaded.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'Official notice archive differs'):
            build.verify_notice_archive(self.notice, self.assets)

    def test_cached_archive_must_pass_its_raw_receipt(self):
        self.cached_archive.write_bytes(self.cached_archive.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'raw SHA512 receipt'):
            build.verify_notice_archive(self.notice, self.assets)

    def test_cached_content_receipt_must_match_the_dependency(self):
        self.metadata.write_text(json.dumps({'contentHash': 'different'}))
        with self.assertRaisesRegex(ValueError, 'Cached NuGet content hash differs'):
            build.verify_notice_archive(self.notice, self.assets)

    def test_project_assets_must_match_the_published_dependency(self):
        self.assets['libraries']['Fixture.Package/1.0.0']['sha512'] = 'different'
        with self.assertRaisesRegex(ValueError, 'restore metadata'):
            build.verify_notice_archive(self.notice, self.assets)

    def test_missing_cached_receipts_are_rejected(self):
        self.metadata.unlink()
        with self.assertRaisesRegex(ValueError, 'archive and receipts missing'):
            build.verify_notice_archive(self.notice, self.assets)


if __name__ == '__main__':
    unittest.main()
