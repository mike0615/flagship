import os
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xenadmin_rocky.console_window import ConsoleWindow


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires X display')
class ConsoleWindowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = SimpleNamespace(root=self.root, client=object(), records={'VM': {'vm': {'name_label': 'Test'}}})
        with patch('xenadmin_rocky.console_window.threading.Thread.start'):
            self.viewer = ConsoleWindow(self.app, 'vm')
        self.viewer.rfb = Mock()

    def tearDown(self):
        self.viewer.close()
        self.root.destroy()

    def test_raw_copy_and_resize_preserve_display_pixels(self):
        view = self.viewer
        view.draw(('resize', 3, 1))
        view.draw(('pixels', 0, 0, 2, 1, bytes([255,0,0,0,0,255])))
        self.assertEqual(view.image.get(0, 0), (255, 0, 0))
        self.assertEqual(view.image.get(1, 0), (0, 0, 255))
        # Overlapping copy must use the original source pixels.
        view.draw(('copy', 1, 0, 2, 1, 0, 0))
        self.assertEqual(view.image.get(1, 0), (255, 0, 0))
        self.assertEqual(view.image.get(2, 0), (0, 0, 255))
        view.draw(('resize', 10, 8))
        self.assertEqual((view.image.width(), view.image.height()), (10, 8))

    def test_default_view_only_and_explicit_control_events(self):
        view = self.viewer
        event = SimpleNamespace(keysym_num=0xff0d, char='\r')
        view.key(event, True); view.cad()
        self.assertTrue(view.inputs.empty())
        view.control.set(True)
        view.key(event, True)
        self.assertEqual(view.inputs.get_nowait(), ('key', (0xff0d, True)))
        view.control.set(False)
        view.release()
        self.assertEqual(view.inputs.get_nowait(), ('key', (0xff0d, False)))
        self.assertFalse(view.pressed)

    def test_focus_release_clears_buttons_and_modifiers(self):
        view = self.viewer
        view.pressed = {0xffe3}; view.buttons = 1; view.position = (3, 4)
        view.release()
        self.assertEqual(view.inputs.get_nowait(), ('key', (0xffe3, False)))
        self.assertEqual(view.inputs.get_nowait(), ('pointer', (3, 4, 0)))
        self.assertEqual(view.buttons, 0)

    def test_old_connection_cannot_receive_input_and_poll_closes_tunnel(self):
        view = self.viewer
        tunnel = view.tunnel = Mock()
        view.control.set(True)
        self.app.client = object()
        view.key(SimpleNamespace(keysym_num=65, char='A'), True)
        self.assertTrue(view.inputs.empty())
        view.poll()
        self.assertTrue(view.stop.is_set())
        tunnel.close.assert_called_once()
        self.assertFalse(view.window.winfo_exists())

    def test_input_overflow_closes_without_recursing_during_key_release(self):
        view = self.viewer
        view.pressed = {0xffe3}
        for _ in range(view.inputs.maxsize): view.inputs.put_nowait(('key', (65, True)))
        view.enqueue('key', 65, False)
        self.assertTrue(view.stop.is_set())
        self.assertFalse(view.window.winfo_exists())
        self.assertFalse(view.pressed)

    def test_cad_preserves_a_modifier_already_held_by_operator(self):
        view = self.viewer
        view.control.set(True)
        view.pressed = {0xffe3}
        view.cad()
        events = [view.inputs.get_nowait() for _ in range(view.inputs.qsize())]
        self.assertEqual(events, [('key', (0xffe9, True)), ('key', (0xffff, True)),
                                  ('key', (0xffff, False)), ('key', (0xffe9, False))])
        self.assertEqual(view.pressed, {0xffe3})

    def test_error_is_visible_and_disables_control(self):
        self.viewer.control.set(True)
        self.viewer.draw(('error', 'ConsoleError'))
        self.assertFalse(self.viewer.control.get())
        self.assertIn('Close and reopen', self.viewer.status.get())

    def test_closing_console_cancels_its_pending_callback_while_parent_lives(self):
        errors = []
        self.root.tk.createcommand('bgerror', errors.append)
        self.viewer.close()
        self.root.after(80, self.root.quit)
        self.root.mainloop()
        self.assertFalse(errors, errors)
        self.assertTrue(self.root.winfo_exists())


if __name__ == '__main__': unittest.main()
