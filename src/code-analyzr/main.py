"""
    Usage example:
    Analyze a file "example.py" with Python 3.8, encoding utf-8, and save the result in "result.json":
        python main.py example.py --version 3.8 --encoding utf-8 --output result.json

    Analyze a file "example.py", but only the functions "func1" and "func2":
        python main.py example.py --analyze func1,func2

    Analyze a file "example.py", but ignore the functions "func3" and "func4":
        python main.py example.py --ignore func3,func4
"""

import argparse
import sys

from analyzr import AstAnalyzr


def main():
    parser = argparse.ArgumentParser(description="Analyse Python code.")
    parser.add_argument("file", help="Path to the Python file to analyze")
    parser.add_argument(
        "--version",
        default="3.8",
        help="Python version to use for analysis. Default is 3.8.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding of the file. Default is utf-8.",
    )
    parser.add_argument(
        "--analyze",
        default=None,
        help="Comma-separated list of functions to analyze.",
    )
    parser.add_argument(
        "--ignore",
        default=None,
        help="Comma-separated list of functions to ignore.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save the analysis result as JSON. If not specified, prints to console.",
    )

    args = parser.parse_args()

    try:
        with open(args.file, "r", encoding=args.encoding) as f:
            code = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    analyzer = AstAnalyzr(
        code,
        functions_to_analyze=args.analyze,
        ignore=args.ignore,
        version=tuple(map(int, args.version.split("."))),
    )
    result = analyzer.get_analyse()

    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(result)
            print(f"Analysis result saved to {args.output}")
        except Exception as e:
            print(f"Error writing to output file: {e}")
    else:
        print(result)


if __name__ == "__main__":
    main()
