import json
import os
import sys
import unittest

PACKAGE_PARENT = "../../src/code_analyzr"
sys.path.append(PACKAGE_PARENT)

from analyzr import AstAnalyzr

from configuration import CodeAnalyzrConfiguration


class AstAnalyzrTest(unittest.TestCase):
    maxDiff = None

    def _test_template(self, test_name):
        test_result_path = os.path.abspath(f"templateTest/{test_name}.json")
        file_test_path = os.path.abspath(f"templateTest/{test_name}.py")

        configuration = CodeAnalyzrConfiguration()

        with open(file_test_path, "r") as f:
            analyzr = AstAnalyzr(configuration=configuration, code_str=f.read())
            result = json.loads(analyzr.get_analyse())
        with open(test_result_path, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_simple(self):
        self._test_template("simpleTest")

    def test_import(self):
        self._test_template("importTest")

    def test_importFrom(self):
        self._test_template("importFromTest")

    def test_simpletype(self):
        self._test_template("simpleTypeTest")

    def test_list(self):
        self._test_template("listTest")

    def test_tuple(self):
        self._test_template("tupleTest")

    def test_nestedFunction(self):
        self._test_template("nestedFunctionTest")

    def test_return(self):
        self._test_template("returnTest")


if __name__ == "__main__":
    unittest.main()
