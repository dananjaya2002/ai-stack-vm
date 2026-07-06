from typing import Dict, List


Character = Dict[str, str]


def load_demo_data() -> List[Character]:
    """Return fictional records used by the demo code search flow."""
    return [
        {
            "name": "Elyndor Vael",
            "role": "Memory architect",
            "artifact": "Heart of Memory",
            "fact": "His compass points toward unresolved questions.",
        },
        {
            "name": "Lysara Thornwind",
            "role": "Skyship captain",
            "artifact": "Aurora's Edge",
            "fact": "She mapped storm-lanes above the Saffron Expanse.",
        },
    ]


def format_character_summary(character: Character) -> str:
    """Format one character as a compact single-line summary."""
    return (
        f"{character['name']} was a {character['role']} connected to "
        f"{character['artifact']}. Notable fact: {character['fact']}"
    )


def build_report(characters: List[Character]) -> str:
    """Build the text report printed by the sample app."""
    summaries = [format_character_summary(character) for character in characters]
    return "\n".join(summaries)
