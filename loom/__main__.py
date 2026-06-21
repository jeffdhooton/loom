import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print("loom — DISCOVER->PLAN->EXECUTE->VERIFY->ITERATE loop engine")
        print("usage: loom {run|resume|ls|logs} ...")
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
