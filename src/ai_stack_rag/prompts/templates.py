"""Named prompt renderers shared by RAG services."""


def memory_answer(question: str, context: str) -> str:
    return f"Use the following memory context to answer the question.\n\n{context}\n\nQuestion: {question}"


def code_answer(question: str, context: str) -> str:
    return f"Use the following code context to answer the question with source references.\n\n{context}\n\nQuestion: {question}"


def evidence_answer(question: str, evidence: str) -> str:
    return f"Answer using only the supplied evidence and cite its source locations.\n\n{evidence}\n\nQuestion: {question}"


def memory_rag_prompt(query: str, contexts: list[str]) -> str:
    if not contexts:
        return f"""
QUESTION:
{query}

Answer clearly and practically.
"""
    context_text = "\n\n".join(contexts)
    return f"""
You are a senior software engineering assistant.

Use the memory context below ONLY if it is relevant.

================ MEMORY =================
{context_text}
=========================================

QUESTION:
{query}

INSTRUCTIONS:
- Be clear and structured
- Use memory when relevant
- Ignore irrelevant memory
"""


def code_rag_prompt(user_question: str, code_context: str) -> str:
    return f"""
You are a private repo-aware coding agent running inside VS Code through Continue.dev.

You have access to retrieved project code chunks from Qdrant.

Rules:
- Use the retrieved code context first.
- Use Symbol Type and Symbol Name to identify relevant functions, classes, components, routes, or documentation sections.
- Do not invent files, functions, APIs, or project structure.
- If context is insufficient, clearly say what extra file or context is needed.
- Prefer minimal, safe, maintainable code changes.
- For implementation tasks, provide a short plan before code.
- For debugging tasks, explain likely cause and verification command.
- Mention affected files when possible.
- Refer to files using the exact Location values from the retrieved context.
- Cite locations inline. Never use numbered source labels such as [Source 1].
- Do not add a numbered Sources section.
- If you suggest commands, keep them specific.
- If multiple files are involved, explain how they connect.

Retrieved code context:

{code_context}

User request:

{user_question}
""".strip()
