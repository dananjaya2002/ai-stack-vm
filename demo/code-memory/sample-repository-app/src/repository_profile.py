from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryProfile:
    name: str
    purpose: str
    owner: str
    primary_module: str


def load_repository_profile() -> RepositoryProfile:
    """Return metadata for the repository browser demo project."""
    return RepositoryProfile(
        name="sample-repository-app",
        purpose="Demonstrate code repository browsing and indexing.",
        owner="AI Stack demo",
        primary_module="repository_summary",
    )
