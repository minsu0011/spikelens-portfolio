"""Regression tests for fail-closed publication rules; no actual private assets."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import public_leakage_guard as guard


class PublicGuardTest(unittest.TestCase):
    def inspect(self, name, body, allow=True):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(body, encoding="utf-8")
            with patch.object(guard, "ROOT", root):
                return guard.inspect([name], {name} if allow else set())

    def test_new_unreviewed_file_fails(self):
        self.assertTrue(self.inspect("new.txt", "hello", allow=False))

    def test_environment_and_binary_types_fail(self):
        self.assertTrue(self.inspect(".env", "EXAMPLE=placeholder"))
        self.assertTrue(self.inspect("example.onnx", "not-a-real-model"))

    def test_prediction_dependency_fails(self):
        self.assertTrue(self.inspect("app/providers/other.py", "import " + "torch"))

    def test_orm_tables_are_allowed(self):
        self.assertEqual(self.inspect("backend/app/models/example.py", "from sqlalchemy import Column\n"), [])

    def test_personal_path_is_rejected(self):
        path = "C:" + "\\Users\\" + "fictional-demo\\file.txt"
        self.assertTrue(self.inspect("example.txt", path))


if __name__ == "__main__":
    unittest.main()
