import re

from langchain_chroma import Chroma


METADATA_QUERY = re.compile(
    r"\b(title|author|authors|wrote|paper called|abstract|affiliation)\b",
    re.IGNORECASE,
)


def get_relevant_context(
    vectorstore: Chroma,
    query: str,
    k: int = 5,
) -> str:
    if vectorstore is None:
        return ""

    docs = vectorstore.similarity_search(query, k=k)

    if METADATA_QUERY.search(query):
        front_matter = vectorstore.similarity_search(
            query,
            k=1,
            filter={"section": "front_matter"},
        )
        docs = front_matter + docs

    unique_docs = []
    seen = set()

    for doc in docs:
        key = (
            doc.metadata.get("page_number"),
            doc.metadata.get("line_start"),
            doc.page_content,
        )
        if key not in seen:
            seen.add(key)
            unique_docs.append(doc)

    return "\n\n---\n\n".join(
        (
            f"[PDF page {doc.metadata.get('page_number', '?')}, "
            f"lines {doc.metadata.get('line_start', '?')}-"
            f"{doc.metadata.get('line_end', '?')}]\n"
            f"{doc.page_content}"
        )
        for doc in unique_docs
    )