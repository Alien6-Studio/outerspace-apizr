import os
import sys
import unittest

PACKAGE_PARENT = "../../src/notebook_transformr"
sys.path.append(PACKAGE_PARENT)

from transformr import NotebookTransformr


class NotebookTransformrTest(unittest.TestCase):
    @staticmethod
    def run_test_on_notebook(notebook_name):
        """
        Helper method to transform a notebook into a script.
        """
        # Define paths
        file_test_path = os.path.abspath(f"templateTest/{notebook_name}.ipynb")
        output_dir = os.path.join(os.getcwd(), ".output")

        # Ensure the output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create an instance of the transformer and convert notebook to script
        transformer = NotebookTransformr()
        source, _ = transformer.convert_notebook(file_test_path)
        output_path = transformer.save_script(
            source, output_dir, os.path.basename(file_test_path)
        )

        return output_path

    def test_empty_notebook(self):
        """
        Test the transformation of an empty notebook.
        """
        output_path = self.run_test_on_notebook("emptyTest")
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r") as file:
            content = file.read()
            self.assertEqual(content.strip(), "")

    def test_simple_notebook(self):
        """
        Test the transformation of a simple notebook with basic operations.
        """
        output_path = self.run_test_on_notebook("simpleTest")
        self.assertTrue(os.path.exists(output_path))

    def test_import_notebook(self):
        """
        Test the transformation of a notebook with library imports.
        """
        output_path = self.run_test_on_notebook("importTest")
        self.assertTrue(os.path.exists(output_path))

        # Assert that the requirements.txt file was created successfully
        requirements_path = os.path.join(os.getcwd(), "output", "requirements.txt")
        self.assertTrue(os.path.exists(requirements_path))

    def test_ipython_syntax(self):
        """
        Test the transformation of a notebook with IPython-specific syntax.
        """
        output_path = self.run_test_on_notebook("ipythonTest")
        self.assertTrue(os.path.exists(output_path))

    def test_special_characters(self):
        """
        Test the transformation of a notebook containing special characters.
        """
        output_path = self.run_test_on_notebook("specialTest")
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, "r", encoding="utf-8") as file:
            content = file.read()
            self.assertIn("é, ñ, ü", content)

    def test_pep8_syntax(self):
        """
        Test the transformation of a notebook with PEP 8 style considerations.
        """
        output_path = self.run_test_on_notebook("pep8Test")
        self.assertTrue(os.path.exists(output_path))

    def test_basic_notebook(self):
        """
        Test the transformation of a basic notebook with elementary operations.
        """
        output_path = self.run_test_on_notebook("basic_notebook")
        self.assertTrue(os.path.exists(output_path))

    def test_dependencies_notebook(self):
        """
        Test the transformation of a notebook with external library dependencies.
        """
        output_path = self.run_test_on_notebook("dependencies_notebook")
        self.assertTrue(os.path.exists(output_path))

    def test_interactive_notebook(self):
        """
        Test the transformation of an interactive notebook with user inputs.
        """
        output_path = self.run_test_on_notebook("interactive_notebook")
        self.assertTrue(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
