import re

from langchain_chroma import Chroma


METADATA_QUERY = re.compile(
    r"\b(title|author|authors|wrote|paper called|abstract|affiliation)\b",
    re.IGNORECASE,
)


def format_knowledge_docs(docs) -> str:
    """把知识库切片格式化成可注入提示的中文上下文。"""
    unique_docs = []
    seen = set()

    for doc in docs:
        key = (
            doc.metadata.get("source"),
            doc.metadata.get("start_index"),
            doc.page_content,
        )
        if key not in seen:
            seen.add(key)
            unique_docs.append(doc)

    return "\n\n---\n\n".join(
        (
            f"[知识点：{doc.metadata.get('topic', '未标注')}"
            f"｜分类：{doc.metadata.get('category', '未标注')}"
            f"｜来源：{doc.metadata.get('source', '未标注')}]\n"
            f"{doc.page_content}"
        )
        for doc in unique_docs
    )


def get_knowledge_context(
    vectorstore: Chroma | None,
    query: str,
    k: int = 4,
) -> str:
    """常驻八股知识库检索。没有库就返回空串，调用方不用关心是否初始化过。"""
    if vectorstore is None:
        return ""
    docs = vectorstore.similarity_search(query, k=k)
    return format_knowledge_docs(docs)


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
