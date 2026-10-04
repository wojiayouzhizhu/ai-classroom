"""构建常驻八股知识库。

用法（在 backend/ 目录下，用 venv 的 python）：
    python build_kb.py                    # 构建并自检
    python build_kb.py --query "TCP 为什么三次握手"   # 只做检索自检

首次运行会下载中文 embedding 模型（约 100MB），之后走缓存。
知识文档在仓库根的 knowledge/ 目录，向量库落在 backend/chroma_kb/。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv()

from agent.rag.indexer import build_knowledge_index, load_knowledge_index

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_DIR = BACKEND_DIR.parents[1] / "knowledge"
DEFAULT_PERSIST_DIR = BACKEND_DIR / "chroma_kb"
COLLECTION_NAME = "cs_basics"


def drop_collection(persist_dir: str) -> None:
    """删掉同名 collection，保证重建是幂等的。"""
    if not Path(persist_dir).exists():
        return
    try:
        import chromadb

        client = chromadb.PersistentClient(path=persist_dir)
        client.delete_collection(name=COLLECTION_NAME)
        print("已清理旧 collection：%s" % COLLECTION_NAME)
    except Exception as exc:
        print("清理旧 collection 跳过（%s：%s）" % (type(exc).__name__, exc))


def self_check(store, queries):
    print()
    print("=== 检索自检 ===")
    for query in queries:
        docs = store.similarity_search(query, k=2)
        print()
        print("问：%s" % query)
        for i, doc in enumerate(docs, 1):
            print(
                "  %d. [%s / %s] %s"
                % (
                    i,
                    doc.metadata.get("topic"),
                    doc.metadata.get("category"),
                    doc.page_content[:80].replace("\n", " "),
                )
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge-dir", default=str(DEFAULT_KNOWLEDGE_DIR))
    parser.add_argument("--persist-dir", default=str(DEFAULT_PERSIST_DIR))
    parser.add_argument("--query", action="append", default=[])
    args = parser.parse_args()

    queries = args.query or [
        "TCP 为什么是三次握手",
        "死锁的必要条件",
        "进程和线程的区别",
    ]

    if not Path(args.knowledge_dir).is_dir():
        print("知识目录不存在：%s" % args.knowledge_dir)
        return 1

    print("知识目录：%s" % args.knowledge_dir)
    print("向量库：%s" % args.persist_dir)

    # 持久化库是追加语义，重建前必须清掉旧 collection，
    # 否则每次构建都会翻倍（66 → 132 → 264...），检索里混进重复片段。
    drop_collection(args.persist_dir)

    print("正在构建（首次要下载中文 embedding 模型，请耐心等待）...")

    store = build_knowledge_index(
        knowledge_dir=args.knowledge_dir,
        collection_name=COLLECTION_NAME,
        persist_directory=args.persist_dir,
    )

    count = store._collection.count()
    print()
    print("构建完成，切片数：%d" % count)

    self_check(store, queries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
