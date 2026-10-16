import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'scripts'))
from package_plugin import package_files, stage_package


class PackageTest(unittest.TestCase):
    def test_runtime_and_documentation_are_self_contained(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'package'
            hashes=stage_package(dest)
            self.assertIn('scripts/install.py',hashes)
            self.assertIn('scripts/package_plugin.py',hashes)
            self.assertIn('package-files.json',hashes)
            self.assertFalse((dest/'node_modules').exists())
            self.assertFalse((dest/'artifacts').exists())
            self.assertEqual((dest/'model.luau').read_bytes(),(PROJECT/'model.luau').read_bytes())

    def test_unsafe_and_private_paths_are_never_published(self):
        for name in ['../private.txt','/etc/passwd','.env','artifacts/trace.json','node_modules/pkg.js']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                project=Path(folder)
                (project/'package-files.json').write_text(json.dumps({'runtime':[name]}))
                if not name.startswith(('../','/')):
                    path=project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('private')
                with self.assertRaises(ValueError):package_files(project)

    def test_symlink_is_not_packaged(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder);(project/'file').write_text('source')
            (project/'link').symlink_to(project/'file')
            (project/'package-files.json').write_text(json.dumps({'runtime':['link']}))
            with self.assertRaises(ValueError):package_files(project)


if __name__=='__main__':
    unittest.main()
