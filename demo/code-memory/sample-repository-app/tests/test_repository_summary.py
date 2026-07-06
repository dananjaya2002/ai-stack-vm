from src.repository_profile import RepositoryProfile
from src.repository_summary import describe_repository


def test_describe_repository_mentions_name_and_module() -> None:
    profile = RepositoryProfile(
        name="sample-repository-app",
        purpose="Demonstrate repository browsing.",
        owner="AI Stack demo",
        primary_module="repository_summary",
    )

    summary = describe_repository(profile)

    assert "sample-repository-app" in summary
    assert "repository_summary" in summary
