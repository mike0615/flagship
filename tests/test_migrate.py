"""First-run journal/config copy from XenAdmin Rocky is non-destructive."""
import os
import tempfile
import unittest
from pathlib import Path

from flagship.migrate import MARKER, migrate_legacy


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.old_xdg_config = os.environ.get('XDG_CONFIG_HOME')
        self.old_xdg_state = os.environ.get('XDG_STATE_HOME')
        os.environ['XDG_CONFIG_HOME'] = str(self.home / 'config')
        os.environ['XDG_STATE_HOME'] = str(self.home / 'state')

    def tearDown(self):
        if self.old_xdg_config is None:
            os.environ.pop('XDG_CONFIG_HOME', None)
        else:
            os.environ['XDG_CONFIG_HOME'] = self.old_xdg_config
        if self.old_xdg_state is None:
            os.environ.pop('XDG_STATE_HOME', None)
        else:
            os.environ['XDG_STATE_HOME'] = self.old_xdg_state
        self.temp.cleanup()

    def test_copies_journals_and_leaves_originals(self):
        old = self.home / 'state' / 'xenadmin-rocky' / 'journals'
        old.mkdir(parents=True)
        sample = old / 'operations-legacy.jsonl'
        sample.write_text('{"event":"begin"}\n', encoding='utf-8')
        message = migrate_legacy()
        new = self.home / 'state' / 'flagship' / 'journals' / 'operations-legacy.jsonl'
        self.assertTrue(new.is_file())
        self.assertEqual(new.read_text(encoding='utf-8'), '{"event":"begin"}\n')
        self.assertTrue(sample.is_file(), 'original journal must be left in place')
        self.assertIsNotNone(message)
        self.assertTrue((self.home / 'state' / 'flagship' / MARKER).is_file())
        # A second run must not invent a second copy or alter the original.
        self.assertIsNone(migrate_legacy())

    def test_does_nothing_without_legacy_data(self):
        self.assertIsNone(migrate_legacy())
        self.assertFalse((self.home / 'state' / 'flagship').exists())

    def test_skips_when_flagship_state_already_exists(self):
        (self.home / 'state' / 'flagship').mkdir(parents=True)
        old = self.home / 'state' / 'xenadmin-rocky' / 'journals'
        old.mkdir(parents=True)
        (old / 'operations-legacy.jsonl').write_text('x\n', encoding='utf-8')
        self.assertIsNone(migrate_legacy())
        self.assertFalse((self.home / 'state' / 'flagship' / 'journals' / 'operations-legacy.jsonl').exists())
