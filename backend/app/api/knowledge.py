"""
Knowledge API 端点
提供知识库检索、文档上传、管理功能
"""

from typing import Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from langchain_core.documents import Document

from app.knowledge.retriever import get_retriever


router = APIRouter()


class SearchRequest(BaseModel):
    """知识检索请求"""
    query: str = Field(description="检索查询")
    k: int = Field(default=5, ge=1, le=20, description="返回结果数量")


class DocumentResult(BaseModel):
    """文档结果"""
    content: str = Field(description="文档内容")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    score: float | None = Field(default=None, description="相似度分数")


class SearchResponse(BaseModel):
    """检索响应"""
    results: list[DocumentResult]
    total: int
    query: str


class AddDocumentRequest(BaseModel):
    """添加文档请求"""
    content: str = Field(description="文档内容")
    title: str | None = Field(default=None, description="文档标题")
    source: str | None = Field(default=None, description="文档来源")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class AddDocumentResponse(BaseModel):
    """添加文档响应"""
    success: bool
    message: str
    doc_count: int = Field(description="添加的文档数量")


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest):
    """检索知识库

    Args:
        request: 检索请求，包含查询和返回数量

    Returns:
        检索结果列表
    """
    retriever = get_retriever()

    try:
        # 使用带分数的检索
        results = retriever.search_with_score(request.query, k=request.k)

        doc_results = []
        for doc, score in results:
            doc_results.append(DocumentResult(
                content=doc.page_content,
                metadata=doc.metadata,
                score=float(score),
            ))

        return SearchResponse(
            results=doc_results,
            total=len(doc_results),
            query=request.query,
        )
    except Exception as e:
        # 如果知识库为空或其他错误
        return SearchResponse(
            results=[],
            total=0,
            query=request.query,
        )


@router.post("/add", response_model=AddDocumentResponse)
async def add_document(request: AddDocumentRequest):
    """添加单个文档到知识库

    Args:
        request: 文档内容和元数据

    Returns:
        添加结果
    """
    retriever = get_retriever()

    # 构建元数据
    metadata = request.metadata.copy()
    if request.title:
        metadata["title"] = request.title
    if request.source:
        metadata["source"] = request.source

    # 创建文档
    doc = Document(
        page_content=request.content,
        metadata=metadata,
    )

    try:
        retriever.add_documents([doc])
        return AddDocumentResponse(
            success=True,
            message="文档添加成功",
            doc_count=1,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加文档失败: {str(e)}")


@router.post("/upload", response_model=AddDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(None),
    source: str = Form(None),
):
    """上传文档文件

    支持 .txt, .md 文件格式

    Args:
        file: 上传的文件
        title: 文档标题
        source: 文档来源

    Returns:
        上传结果
    """
    retriever = get_retriever()

    # 检查文件类型
    allowed_extensions = [".txt", ".md"]
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。支持: {', '.join(allowed_extensions)}",
        )

    try:
        # 读取文件内容
        content = await file.read()
        text_content = content.decode("utf-8")

        # 构建元数据
        metadata = {
            "filename": file.filename,
            "content_type": file.content_type,
        }
        if title:
            metadata["title"] = title
        if source:
            metadata["source"] = source

        # 简单分块：按段落分割
        paragraphs = text_content.split("\n\n")
        documents = []

        for i, para in enumerate(paragraphs):
            para = para.strip()
            if para:
                documents.append(Document(
                    page_content=para,
                    metadata={
                        **metadata,
                        "chunk_index": i,
                    },
                ))

        if not documents:
            raise HTTPException(status_code=400, detail="文件内容为空")

        # 添加到知识库
        retriever.add_documents(documents)

        return AddDocumentResponse(
            success=True,
            message=f"文件 '{file.filename}' 上传成功",
            doc_count=len(documents),
        )

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用 UTF-8 编码")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.delete("/clear")
async def clear_knowledge():
    """清空知识库

    危险操作：将删除所有已索引的文档
    """
    retriever = get_retriever()

    try:
        retriever.clear()
        return {"success": True, "message": "知识库已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")


@router.get("/stats")
async def get_stats():
    """获取知识库统计信息"""
    retriever = get_retriever()

    try:
        vectorstore = retriever._get_vectorstore()
        if vectorstore is None:
            return {
                "initialized": False,
                "doc_count": 0,
                "message": "知识库尚未初始化",
            }

        # 尝试获取文档数量
        doc_count = 0
        if hasattr(vectorstore, "index") and vectorstore.index is not None:
            doc_count = vectorstore.index.ntotal

        return {
            "initialized": True,
            "doc_count": doc_count,
            "embedding_model": "text-embedding-v3",
        }
    except Exception as e:
        return {
            "initialized": False,
            "error": str(e),
        }
