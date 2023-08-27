import json
import os
import sys
import unittest

PACKAGE_PARENT = "../../src/fast_apizr"
sys.path.append(PACKAGE_PARENT)

from generator import Analyzr, FastApiAppGenerator, FastApizrConfiguration

HOSTNAME = "0.0.0.0"  # nosec B104

conf: FastApizrConfiguration = FastApizrConfiguration.model_validate(
    {
        "module_name": "main",
        "api_filename": "app.py",
    }
)


class FastAPIAppGeneratorTest(unittest.TestCase):
    maxDiff = None

    def test_return(self):
        os.path.abspath("templateTest/simpleTest.py")
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
