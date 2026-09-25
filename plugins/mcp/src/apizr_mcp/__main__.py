import sys


def main() -> int:
    if sys.argv[1:2] == ["serve"]:
        from .server import main as serve

        return serve(sys.argv[2:])
    from .worker import main as calculate

    return calculate()


if __name__ == "__main__":
    raise SystemExit(main())
