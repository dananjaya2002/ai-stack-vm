from repository_profile import RepositoryProfile, load_repository_profile


def describe_repository(profile: RepositoryProfile | None = None) -> str:
    """Build a short human-readable repository summary."""
    selected = profile or load_repository_profile()
    return (
        f"{selected.name} is owned by {selected.owner}. "
        f"It exists to {selected.purpose.lower()} "
        f"The primary module is {selected.primary_module}."
    )


def main() -> None:
    print(describe_repository())


if __name__ == "__main__":
    main()
