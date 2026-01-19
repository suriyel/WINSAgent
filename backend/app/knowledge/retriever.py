"""
知识库检索器
基于 FAISS 向量数据库
"""

from typing import List
from pathlib import Path
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings

from app.config import get_settings


class KnowledgeRetriever:
    """知识库检索器"""

    def __init__(self):
        self.settings = get_settings()
        self._vectorstore: FAISS | None = None
        self._embeddings = None

    def _get_embeddings(self):
        """获取 Embedding 模型"""
        if self._embeddings is None:
            self._embeddings = DashScopeEmbeddings(
                model="text-embedding-v3",
                dashscope_api_key=self.settings.dashscope_api_key,
            )
        return self._embeddings

    def _get_vectorstore(self) -> FAISS | None:
        """获取向量存储"""
        if self._vectorstore is None:
            index_path = Path(self.settings.faiss_index_path)
            if index_path.exists():
                self._vectorstore = FAISS.load_local(
                    str(index_path),
                    self._get_embeddings(),
                    allow_dangerous_deserialization=True,
                )
        return self._vectorstore

    def search(self, query: str, k: int = 5) -> List[Document]:
        """检索相关文档

        Args:
            query: 检索查询
            k: 返回结果数量

        Returns:
            相关文档列表
        """
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return []

        return vectorstore.similarity_search(query, k=k)

    def search_with_score(
        self, query: str, k: int = 5
    ) -> List[tuple[Document, float]]:
        """检索相关文档（带相似度分数）

        Args:
            query: 检索查询
            k: 返回结果数量

        Returns:
            (文档, 相似度分数) 列表
        """
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return []

        return vectorstore.similarity_search_with_score(query, k=k)

    def add_documents(self, documents: List[Document]):
        """添加文档到知识库

        Args:
            documents: 要添加的文档列表
        """
        vectorstore = self._get_vectorstore()

        if vectorstore is None:
            # 创建新的向量存储
            self._vectorstore = FAISS.from_documents(
                documents, self._get_embeddings()
            )
        else:
            # 添加到现有存储
            vectorstore.add_documents(documents)

        # 保存
        self.save()

    def save(self):
        """保存向量存储到磁盘"""
        if self._vectorstore:
            index_path = Path(self.settings.faiss_index_path)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            self._vectorstore.save_local(str(index_path))

    def clear(self):
        """清空知识库"""
        self._vectorstore = None
        index_path = Path(self.settings.faiss_index_path)
        if index_path.exists():
            import shutil

            shutil.rmtree(index_path)


# 全局实例
_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    """获取知识库检索器单例"""
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever
