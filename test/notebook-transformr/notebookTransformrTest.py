import unittest
import os, sys
import tempfile
import shutil
import asyncio

PACKAGE_PARENT = "../"
SCRIPT_DIR = os.path.dirname(
    os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__)))
)
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))

# pylint: disable=import-error
from transformr import NotebookTransformr


class NotebookTransformrTest(unittest.TestCase):
    def test_empty_notebook(self):
        file_test_path = os.path.abspath("templateTest/emptyTest.ipynb")
        output_dir = os.path.join(os.getcwd(), "output")

        transformer = NotebookTransformr()
        source, _ = transformer.convert_notebook(file_test_path)
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r") as file:
            content = file.read()
            self.assertEqual(content.strip(), "")

    def test_simple_notebook(self):
        file_test_path = os.path.abspath("templateTest/simpleTest.ipynb")
        output_dir = os.path.join(os.getcwd(), "output")

        # Ensure the output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create an instance of the transformer
        transformer = NotebookTransformr()

        # Convert the notebook to a script
        source, _ = transformer.convert_notebook(file_test_path)

        # Save the script to the output directory
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        # Assert that the file was saved successfully
        self.assertTrue(os.path.exists(output_path))

        with open(output_path, "r") as file:
            content = file.read()
            print(content)

    def test_import_notebook(self):
        file_test_path = os.path.abspath("templateTest/importTest.ipynb")
        output_dir = os.path.join(os.getcwd(), "output")

        # Ensure the output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create an instance of the transformer
        transformer = NotebookTransformr()

        # Convert the notebook to a script
        source, _ = transformer.convert_notebook(file_test_path)

        # Save the script to the output directory
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        # Assert that the file was saved successfully
        self.assertTrue(os.path.exists(output_path))

        # Assert that the requirements.txt file was created successfully
        requirements_path = os.path.join(output_dir, "requirements.txt")
        self.assertTrue(os.path.exists(requirements_path))

        with open(output_path, "r") as file:
            content = file.read()
            print(content)

    def test_ipython_syntax(self):
        file_test_path = os.path.abspath("templateTest/ipythonTest.ipynb")
        output_dir = os.path.join(os.getcwd(), "output")

        transformer = NotebookTransformr()
        source, _ = transformer.convert_notebook(file_test_path)
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        self.assertTrue(os.path.exists(output_path))

    def test_special_characters(self):
        file_test_path = os.path.abspath("templateTest/specialTest.ipynb")
        output_dir = os.path.join(os.getcwd(), "output")

        transformer = NotebookTransformr()
        source, _ = transformer.convert_notebook(file_test_path)
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r", encoding="utf-8") as file:
            content = file.read()
            self.assertIn("é, ñ, ü", content)

    def test_pep8_syntax(self):
        file_test_path = os.path.abspath("templateTest/pep8Test.ipynb")
        output_dir = os.path.join(os.getcwd(), "output")

        transformer = NotebookTransformr()
        source, _ = transformer.convert_notebook(file_test_path)
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r") as file:
            content = file.read()
            print(content)


if __name__ == "__main__":
    unittest.main()
