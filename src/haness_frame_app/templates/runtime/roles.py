ROLE_ORDER = ["project_scout", "context_curator", "researcher", "planner", "designer", "architect", "critic", "decision_maker", "coder", "reviewer", "escalation"]

ROLE_SUMMARIES = {
    "project_scout": "Searches for related systems, alternatives, and failure modes.",
    "context_curator": "Assembles the business context and internal evidence.",
    "researcher": "Collects supporting evidence and citations.",
    "planner": "Turns evidence into options and tradeoffs.",
    "designer": "Defines user flows and interaction constraints.",
    "architect": "Checks boundaries, data flow, and operational fit.",
    "critic": "Challenges assumptions and missing tests.",
    "decision_maker": "Chooses the accepted option and the implementation brief.",
    "coder": "Implements the accepted plan.",
    "reviewer": "Validates the implementation result.",
    "escalation": "Handles outside-model or higher-risk decisions.",
}


def describe_role(role: str) -> str:
    return ROLE_SUMMARIES.get(role, "")
