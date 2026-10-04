from functools import lru_cache

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document


@lru_cache(maxsize=1)
def get_embeddings() -> FastEmbedEmbeddings:
    return FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")


def build_index(file_path: str, collection_name: str) -> Chroma:
    """Load PDF, split into chunks, embed and store in memory"""

    # PDF load
    loader = PyPDFLoader(file_path)
    documents = loader.load()

    # Split to chunks

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)
    for chunk in chunks:
        page_index = int(chunk.metadata.get("page", 0))
        page_text = documents[page_index].page_content
        start = int(chunk.metadata.get("start_index", 0))

        chunk.metadata.update(
            section="body",
            page_number=page_index + 1,
            line_start=page_text.count("\n", 0, start) + 1,
            line_end=page_text.count("\n", 0, start)
            + chunk.page_content.count("\n")
            + 1,
        )

    first_page = documents[0].page_content
    front_matter = Document(
        page_content=(
            "DOCUMENT FRONT MATTER: title, authors, affiliations and abstract.\n\n"
            + first_page
        ),
        metadata={
            "section": "front_matter",
            "page_number": 1,
            "line_start": 1,
            "line_end": first_page.count("\n") + 1,
        },
    )

    chunks.append(front_matter)
    # Embed and store in memory
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        collection_name=collection_name,
    )
    return vectorstore
