import unittest, sys
import json

import os

PACKAGE_PARENT = "../"
SCRIPT_DIR = os.path.dirname(
    os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__)))
)
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))

from generator import FastApiAppGenerator
from generator import Configuration
from generator import Analyzr

conf: Configuration = Configuration.model_validate(
    {
        "module_name": "main",
        "host": "0.0.0.0",
        "port": 5000,
        "debug": False,
        "api_filename": "app.py",
    }
)


class FastAPIAppGeneratorTest(unittest.TestCase):
    maxDiff = None

    def test_return(self):
        test_result = os.path.abspath("templateTest/simpleTest.py")
        file_test = os.path.abspath("templateTest/simpleTest.json")

        with open(file_test, "r") as f:
            analyse = Analyzr.model_validate_json(f.read())

        result = FastApiAppGenerator(conf, analyse).gen_fastapi_app()

        # Read the expected result
        with open("templateTest/simpleTest.py", "r") as f:
            expect = f.read()

        # Split the strings into lines and strip whitespace from each line
        result_lines = [line.strip() for line in result.splitlines()]
        expect_lines = [line.strip() for line in expect.splitlines()]

        # Compare the cleaned lines
        self.assertEqual(result_lines, expect_lines)


if __name__ == "__main__":
    unittest.main()
