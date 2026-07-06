from utils import build_report, load_demo_data


def main() -> None:
    """Load demo records and print a formatted character report."""
    characters = load_demo_data()
    report = build_report(characters)
    print(report)


if __name__ == "__main__":
    main()
