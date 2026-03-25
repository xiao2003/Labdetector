from __future__ import annotations

import unittest
from unittest.mock import patch

from pc.desktop_app import DesktopApp


class KnowledgeImportDispatchTests(unittest.TestCase):
    def test_dispatch_knowledge_import_reads_tk_state_on_main_thread(self) -> None:
        captured = {}
        app = DesktopApp()
        app.root.withdraw()
        if app.splash is not None and app.splash.winfo_exists():
            app.splash.withdraw()
        try:
            app.kb_reset_var.set(True)
            app.kb_structured_var.set(False)
            app.runtime = type('RuntimeStub', (), {
                'import_knowledge_paths': staticmethod(lambda paths, scope_name='common', reset_index=False, structured=True: {
                    'paths': paths,
                    'scope': scope_name,
                    'reset_index': reset_index,
                    'structured': structured,
                })
            })()

            def _dispatch(name, fn):
                captured['name'] = name
                captured['payload'] = fn()

            app._dispatch = _dispatch
            app._dispatch_knowledge_import(['a.txt'], 'expert.safety.chem_safety_expert')
        finally:
            app.root.destroy()

        self.assertEqual(captured['name'], 'kb_import')
        self.assertEqual(captured['payload']['paths'], ['a.txt'])
        self.assertEqual(captured['payload']['scope'], 'expert.safety.chem_safety_expert')
        self.assertTrue(captured['payload']['reset_index'])
        self.assertFalse(captured['payload']['structured'])


if __name__ == '__main__':
    unittest.main()
