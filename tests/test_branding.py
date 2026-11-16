"""Package name, compatibility shim and About/Help strings."""
import os
import unittest

import flagship
import xenadmin_rocky


class BrandingTests(unittest.TestCase):
    def test_package_metadata(self):
        self.assertEqual(flagship.APP_NAME, 'Flagship')
        self.assertEqual(flagship.__version__, '1.3.0.dev1')
        self.assertEqual(xenadmin_rocky.__version__, flagship.__version__)

    def test_shim_exports_application(self):
        from flagship.app import Application as FlagshipApp
        from xenadmin_rocky.app import Application as CompatApp
        self.assertIs(FlagshipApp, CompatApp)

    def test_about_copy(self):
        from flagship import about_config as about
        self.assertEqual(about.APP_NAME, 'Flagship')
        self.assertIn('cyber chief toolset', about.TOOLSET)
        self.assertIn('https://github.com/mike0615/flagship', dict(about.LINKS).values())
        self.assertIn('BSD 2-Clause', about.LICENSE_NOTICE)
        self.assertIn('not an official XCP-ng', about.CREDITS)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires X display (use xvfb-run)')
class AboutDialogTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from flagship.app import Application
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root)

    def tearDown(self):
        self.app.jobs.shutdown(wait=True)
        self.root.destroy()

    def test_window_title_and_about(self):
        self.assertIn('Flagship', self.root.title())
        self.assertNotIn('XenAdmin', self.root.title())
        dialog = self.app.about()
        self.assertEqual(dialog.window.title(), 'About Flagship')
        dialog.window.destroy()

    def test_help_title(self):
        help_dialog = self.app.help()
        self.assertEqual(help_dialog.window.title(), 'Flagship Help')
        help_dialog.window.destroy()
