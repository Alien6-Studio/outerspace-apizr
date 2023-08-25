import unittest, sys
import json
from pprint import pprint
import os

PACKAGE_PARENT = "../../src/code_analyzr"
sys.path.append(PACKAGE_PARENT)

from analyzr import AstAnalyzr

class AstAnalyzrTest(unittest.TestCase):
    maxDiff = None

    def test_simple(self):
        test_result = os.path.abspath("templateTest/simpleTest.json")
        file_test = os.path.abspath("templateTest/simpleTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_import(self):
        test_result = os.path.abspath("templateTest/importTest.json")
        file_test = os.path.abspath("templateTest/importTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_importFrom(self):
        test_result = os.path.abspath("templateTest/importFromTest.json")
        file_test = os.path.abspath("templateTest/importFromTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_simpletype(self):
        test_result = os.path.abspath("templateTest/simpleTypeTest.json")
        file_test = os.path.abspath("templateTest/simpleTypeTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_list(self):
        test_result = os.path.abspath("templateTest/listTest.json")
        file_test = os.path.abspath("templateTest/listTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_tuple(self):
        test_result = os.path.abspath("templateTest/tupleTest.json")
        file_test = os.path.abspath("templateTest/tupleTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_nestedFunction(self):
        test_result = os.path.abspath("templateTest/nestedFunctionTest.json")
        file_test = os.path.abspath("templateTest/nestedFunctionTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)

    def test_return(self):
        test_result = os.path.abspath("templateTest/returnTest.json")
        file_test = os.path.abspath("templateTest/returnTest.py")

        with open(file_test, "r") as f:
            result = json.loads(
                AstAnalyzr(code_str=f.read(), version=(3, 8)).get_analyse()
            )

        with open(test_result, "r") as f:
            expect = json.loads(f.read())

        self.assertEqual(result, expect)


if __name__ == "__main__":
    unittest.main()
