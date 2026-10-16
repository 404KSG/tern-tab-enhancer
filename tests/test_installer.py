"""The actual installer against an isolated, stateful Tern CLI boundary."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
from types import SimpleNamespace
import shutil

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'scripts'))
import install as installer
MARKER = '// Tern Tab Enhancer Pi bridge.'
FAKE = '''#!/usr/bin/env python3
import json,os,sys,shutil
from pathlib import Path
root=Path(os.environ['TTE_TEST_ROOT']);plugins=root/'config/plugins';plugins.mkdir(parents=True,exist_ok=True)
args=sys.argv[1:];dest=plugins/'tern-tab-enhancer'
with (root/'calls.jsonl').open('a') as out:out.write(json.dumps(args)+'\\n')
if args[:2]==['plugin','dir']:
 print(plugins);raise SystemExit(0)
if args[:2]==['plugin','list']:
 if os.environ.get('TTE_TEST_LIST_FAIL'):raise SystemExit(2)
 print(json.dumps({'plugins':[{'id':'tern-tab-enhancer','status':'ready'}] if dest.exists() else [],'problems':[]}));raise SystemExit(0)
if args[:2]==['plugin','install']:
 if dest.exists():shutil.rmtree(dest)
 shutil.copytree(Path(args[2]),dest)
 if os.environ.get('TTE_TEST_INSTALL_FAIL') and not (root/'failed-once').exists():
  (root/'failed-once').write_text('yes');raise SystemExit(3)
 print(json.dumps({'id':'tern-tab-enhancer','dir':str(dest)}));raise SystemExit(0)
if args[:2]==['plugin','remove']:
 if os.environ.get('TTE_TEST_REMOVE_FAIL'):raise SystemExit(4)
 if dest.exists():shutil.rmtree(dest)
 print(json.dumps({'removed':str(dest)}));raise SystemExit(0)
if args[:2]==['plugin','reload']:
 print('{}');raise SystemExit(0)
raise SystemExit(5)
'''


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tte-installer-')
        self.root = Path(self.temp.name)
        self.tern = self.root/'tern'
        self.tern.write_text(FAKE);self.tern.chmod(0o700)
        self.agent = self.root/'agent'
        self.extension = self.agent/'extensions/tern-tab-enhancer.ts'
        self.plugin = self.root/'config/plugins/tern-tab-enhancer'
        self.env = {**os.environ,'TTE_TEST_ROOT':str(self.root)}

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, *arguments, env=None):
        return subprocess.run(['python3',str(PROJECT/'scripts/install.py'),'--tern',str(self.tern),
                               '--pi-agent-dir',str(self.agent),*arguments],capture_output=True,text=True,
                              env={**self.env,**(env or {})},timeout=15)

    def seed(self):
        self.plugin.mkdir(parents=True)
        (self.plugin/'plugin.toml').write_text('schema = 1\nid = "tern-tab-enhancer"\nversion = "old"\n')
        (self.plugin/'old.txt').write_text('old plugin')
        self.extension.parent.mkdir(parents=True)
        self.extension.write_text(MARKER+' old bridge\n')

    def test_failed_bridge_preflight_does_not_install_tern(self):
        self.extension.parent.parent.mkdir(parents=True)
        self.extension.parent.write_text('not a directory')
        result = self.run_installer()
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.plugin.exists(),result.stdout+result.stderr)

    def test_failed_tern_update_restores_both_old_components(self):
        self.seed()
        old_bridge=self.extension.read_bytes()
        result=self.run_installer('--force',env={'TTE_TEST_INSTALL_FAIL':'1'})
        self.assertNotEqual(result.returncode,0)
        self.assertTrue((self.plugin/'old.txt').exists(),result.stdout+result.stderr)
        self.assertEqual(self.extension.read_bytes(),old_bridge)

    def test_failed_tern_remove_keeps_bridge(self):
        self.seed();old_bridge=self.extension.read_bytes()
        result=self.run_installer('--uninstall',env={'TTE_TEST_REMOVE_FAIL':'1'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.extension.read_bytes(),old_bridge)
        self.assertTrue((self.plugin/'old.txt').exists())

    def test_failed_post_install_catalog_restores_previous_files(self):
        self.seed();old_bridge=self.extension.read_bytes()
        result=self.run_installer('--force',env={'TTE_TEST_LIST_FAIL':'1'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.extension.read_bytes(),old_bridge)
        self.assertTrue((self.plugin/'old.txt').exists())

    def test_failed_first_install_leaves_no_partial_plugin(self):
        result=self.run_installer(env={'TTE_TEST_INSTALL_FAIL':'1'})
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.plugin.exists());self.assertFalse(self.extension.exists())
        self.assertEqual(list(self.extension.parent.glob('.tte-*')),[])

    def test_refuses_symlink_even_when_target_has_our_marker(self):
        self.extension.parent.mkdir(parents=True)
        other=self.root/'user-file';other.write_text(MARKER+' custom\n')
        self.extension.symlink_to(other)
        result=self.run_installer('--force');self.assertNotEqual(result.returncode,0)
        self.assertTrue(self.extension.is_symlink());self.assertEqual(other.read_text(),MARKER+' custom\n')

    def test_failed_rollback_retains_the_existing_backup_without_copying_again(self):
        self.seed();original=shutil.copytree
        retained=[]
        def fail_restore(source,destination,*args,**kwargs):
            if Path(source).name=='old-plugin':
                retained.append(Path(source).parent)
                raise OSError('simulated disk failure during restore')
            return original(source,destination,*args,**kwargs)
        args=SimpleNamespace(tern=str(self.tern),pi_agent_dir=self.agent,without_pi_bridge=False,uninstall=False,force=True)
        try:
            with patch.dict(os.environ,{**self.env,'TTE_TEST_INSTALL_FAIL':'1'}), patch.object(installer.shutil,'copytree',side_effect=fail_restore):
                with self.assertRaises(RuntimeError):installer.transact(args)
            self.assertTrue(retained)
            self.assertTrue((retained[0]/'old-plugin/old.txt').is_file(),'the only backup was deleted')
            self.assertTrue((retained[0]/'old-bridge.ts').is_file())
        finally:
            for folder in set(retained):
                if folder.exists():shutil.rmtree(folder)

    def test_normal_install_and_uninstall(self):
        result=self.run_installer();self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(self.extension.exists());self.assertTrue((self.plugin/'plugin.toml').exists())
        self.assertFalse((self.plugin/'node_modules').exists());self.assertFalse((self.plugin/'artifacts').exists())
        result=self.run_installer('--uninstall');self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(self.extension.exists());self.assertFalse(self.plugin.exists())

    def test_refuses_to_overwrite_unrelated_bridge(self):
        self.extension.parent.mkdir(parents=True);self.extension.write_text('// user extension\n')
        result=self.run_installer('--force');self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.extension.read_text(),'// user extension\n');self.assertFalse(self.plugin.exists())

    def test_without_bridge_leaves_existing_pi_extension_alone(self):
        self.extension.parent.mkdir(parents=True);self.extension.write_text('// unrelated\n')
        result=self.run_installer('--without-pi-bridge');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.extension.read_text(),'// unrelated\n')


if __name__ == '__main__':
    unittest.main()
