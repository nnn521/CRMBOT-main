"""
知识库检索节点 (RAG) - 回答汽车产品相关问题

重构要点：
1. 使用本地 OllamaEmbeddings + bge-m3 模型
2. 使用 langchain_text_splitters 最新导入路径
3. 【多模态升级】知识库改为保时捷/比亚迪汽车产品知识
4. 防御性编程：任何情况下不报错，返回干净 state
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional

from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompts import guard_system_prompt, guard_user_content
from app.services.image_service import find_car_images, requested_image_count
from app.agents.state import SalesState, strip_messages

logger = get_logger("knowledge_node")

# FAISS 返回的是平方 L2 距离。Ollama bge-m3 输出归一化向量，
# 平方 L2 = 2 - 2·cos(相似度)：阈值 1.2 约等于 cos ≥ 0.4 才保留，
# 低于该相似度的结果视为噪声丢弃。
RELEVANCE_THRESHOLD = 1.2


# ═══════════════════════════════════════════════════════════════
# 默认产品知识库（当目录为空时自动生成）
# ═══════════════════════════════════════════════════════════════

DEFAULT_KNOWLEDGE_BASE = """# 丰田汽车产品知识库

欢迎来到丰田汽车知识库，包含广汽丰田、一汽丰田及进口丰田全系车型。

## 轿车系列

### 凯美瑞（CAMRY）
- 指导价：17.18-25.98万
- 2.0G 豪华版：18.98万
- 双擎混动版油耗低至4.1L/100km
- TNGA架构，Toyota Safety Sense智驾系统

### 雷凌（LEVIN）
- 指导价：11.38-14.88万
- 入门级家用轿车首选
- 双擎混动版百公里油耗约4L

### 亚洲龙（AVALON）
- 指导价：17.88-25.68万
- B+级轿车，空间越级

### 丰田bZ3
- 指导价：10.98-19.98万
- 纯电轿车

## SUV系列

### 汉兰达（HIGHLANDER）
- 指导价：24.98-32.58万
- 双擎2.5L四驱豪华版：29.28万
- 7座布局，中型SUV标杆
- 口碑保值率极高

### RAV4荣放
- 指导价：16.98-23.88万
- 全球畅销SUV

### 普拉多（PRADO）
- 指导价：44.98-55.98万
- 全新2.4T混动，硬派越野

### 锋兰达
- 指导价：13.28-17.28万
- 高性价比紧凑型SUV

### 卡罗拉锐放（COROLLA CROSS）
- 指导价：12.68-18.48万

### 威兰达
- 指导价：16.98-23.08万

### 皇冠陆放
- 指导价：28.48-33.28万
- 汉兰达姊妹车型

### 凌放HARRIER
- 指导价：19.18-29.88万

## MPV系列

### 赛那SIENNA
- 指导价：29.98-39.38万
- 豪华家用MPV，空间灵活

### 格瑞维亚（GRANVIA）
- 指导价：29.98-41.68万

## 进口车型

### 埃尔法（ALPHARD）
- 指导价：89.90-92.90万
- 豪华MPV标杆

### 威尔法（VELLFIRE）
- 指导价：89.90-92.90万

### 皇冠SportCross
- 指导价：36.90-42.90万

### SUPRA
- 指导价：49.90-62.90万
- 丰田传奇跑车

## 新能源系列

### 铂智系列
- 铂智3X：10.98-15.98万
- 铂智4X：17.98-23.88万
- 铂智7：16.98-22.98万

### 丰田bZ系列
- bZ3：10.98-19.98万
- bZ5：12.98-19.98万

## 销售政策
- 所有价格均为官方指导价（万元）
- 丰田提供3年或10万公里质保
- 支持金融分期：低首付/免息/低息方案
- 店内优惠以实际到店洽谈为准
"""


# ═══════════════════════════════════════════════════════════════
# 知识库服务类
# ═══════════════════════════════════════════════════════════════

class KnowledgeBaseService:
    """
    知识库服务 - 封装 RAG 相关操作
    
    防御性设计原则：
    1. 初始化失败不抛异常，返回空向量库
    2. 检索失败返回空列表而非报错
    3. 知识库为空时自动生成测试文档
    """
    
    def __init__(self):
        self.embeddings: Optional[OllamaEmbeddings] = None
        self.vector_store: Optional[FAISS] = None
        self._initialized: bool = False
        self._init_error: Optional[str] = None
        # 并发保护：冷启动时多个请求同时触发 initialize() 只会建一次索引
        self._lock = asyncio.Lock()

    # ═══════════════════════════════════════════════════════════
    # 安全持久化：不依赖 pickle 反序列化
    # ═══════════════════════════════════════════════════════════
    #
    # FAISS.load_local 需要 allow_dangerous_deserialization=True 才能读取
    # index.pkl（pickle 反序列化 = 任意代码执行）。生产环境不能打开该开关，
    # 因此改为：
    #   1. 优先读取 kb_documents.json（纯 JSON，无代码执行风险）；
    #   2. 无 JSON 时从 knowledge_base 目录的源文档重建索引；
    #   3. 重建后写出 JSON 快照，下次启动直接复用（仍需重新 embedding）。

    def _documents_snapshot_path(self) -> str:
        return os.path.join(settings.vector_store_path, "kb_documents.json")

    def _write_documents_snapshot(self, documents: List) -> None:
        """把切片后的文本块写入 JSON 快照（原子替换，失败不影响主流程）。"""
        try:
            os.makedirs(settings.vector_store_path, exist_ok=True)
            payload = [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata if isinstance(doc.metadata, dict) else {},
                }
                for doc in documents
            ]
            target = self._documents_snapshot_path()
            tmp = f"{target}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp, target)
            logger.info(f"[KB] 文档快照已写入: {target} ({len(payload)} 块)")
        except Exception as e:
            logger.warning(f"[KB] 文档快照写入失败（非阻塞）: {e}")

    def _read_documents_snapshot(self) -> Optional[List]:
        """读取 JSON 快照；不存在或损坏时返回 None。"""
        path = self._documents_snapshot_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, list) or not payload:
                return None
            # 延迟导入，避免模块级额外依赖
            from langchain_core.documents import Document

            documents = [
                Document(
                    page_content=str(item.get("content", "")),
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                )
                for item in payload
                if isinstance(item, dict) and item.get("content")
            ]
            logger.info(f"[KB] 已读取文档快照: {len(documents)} 块")
            return documents or None
        except Exception as e:
            logger.warning(f"[KB] 文档快照读取失败: {e}")
            return None

    def _ensure_knowledge_base_dir(self) -> str:
        """
        确保知识库目录存在
        
        如果目录不存在，创建目录并生成默认测试文档
        绝不使用无意义的"初始化文档"占位符
        """
        kb_path = os.path.abspath(settings.knowledge_base_path)
        
        # 创建目录
        if not os.path.exists(kb_path):
            try:
                os.makedirs(kb_path, exist_ok=True)
                logger.info(f"[KB] 创建知识库目录: {kb_path}")
            except Exception as e:
                logger.error(f"[KB] 创建目录失败: {e}")
                return kb_path
        
        # 检查目录是否为空
        try:
            files = [f for f in os.listdir(kb_path) 
                     if f.endswith(('.txt', '.md')) and not f.startswith('.')]
            
            if not files:
                logger.warning(f"[KB] 知识库目录为空，生成默认测试文档")
                self._generate_default_knowledge_base(kb_path)
        except Exception as e:
            logger.error(f"[KB] 检查目录内容失败: {e}")
        
        return kb_path
    
    def _generate_default_knowledge_base(self, kb_path: str):
        """
        生成默认知识库文档（含真实产品价格）
        
        绝不使用无意义的"初始化文档"，而是提供有效的产品信息
        """
        try:
            default_file = os.path.join(kb_path, "product_catalog.md")
            with open(default_file, "w", encoding="utf-8") as f:
                f.write(DEFAULT_KNOWLEDGE_BASE)
            logger.info(f"[KB] 默认知识库已生成: {default_file}")
        except Exception as e:
            logger.error(f"[KB] 生成默认知识库失败: {e}")
    
    def _load_documents_from_directory(self, directory_path: str) -> List:
        """
        从目录加载所有文本文件（.txt 和 .md）
        
        防御性处理：
        - 目录不存在返回空列表
        - 文件读取失败跳过并记录日志
        - 支持 UTF-8 编码，失败时尝试其他编码
        """
        documents = []
        
        if not os.path.exists(directory_path):
            logger.warning(f"[KB] 知识库目录不存在: {directory_path}")
            return documents
        
        supported_extensions = ['.txt', '.md']
        
        try:
            files = os.listdir(directory_path)
            logger.info(f"[KB] 扫描目录，发现 {len(files)} 个文件")
            
            for filename in files:
                file_path = os.path.join(directory_path, filename)
                
                # 跳过目录和隐藏文件
                if not os.path.isfile(file_path) or filename.startswith('.'):
                    continue
                
                ext = os.path.splitext(filename)[1].lower()
                if ext not in supported_extensions:
                    logger.debug(f"[KB] 跳过不支持的文件类型: {filename}")
                    continue
                
                # 尝试加载文件（多编码支持）
                doc = self._load_single_file(file_path, filename)
                if doc:
                    documents.extend(doc)
                    
        except Exception as e:
            logger.error(f"[KB] 遍历知识库目录失败: {e}")
        
        logger.info(f"[KB] 文档加载完成: {len(documents)} 个文档")
        return documents
    
    def _load_single_file(self, file_path: str, filename: str) -> Optional[List]:
        """
        加载单个文件，支持多编码尝试
        
        尝试顺序：UTF-8 → GBK → Latin-1
        """
        encodings = ['utf-8', 'gbk', 'latin-1']
        
        for encoding in encodings:
            try:
                loader = TextLoader(file_path, encoding=encoding)
                docs = loader.load()
                
                # 添加来源元数据
                for doc in docs:
                    doc.metadata['source'] = filename
                    doc.metadata['file_path'] = file_path
                    doc.metadata['encoding'] = encoding
                
                logger.info(f"[KB] 成功加载文件: {filename} ({len(docs)} 个文档, 编码: {encoding})")
                return docs
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"[KB] 加载文件失败 {filename} (编码 {encoding}): {e}")
                continue
        
        logger.error(f"[KB] 无法解码文件: {filename}，已跳过")
        return None
    
    async def _create_vector_store_from_documents(
        self, documents: List, save_snapshot: bool = True
    ) -> Optional[FAISS]:
        """
        从文档创建向量存储

        使用 RecursiveCharacterTextSplitter 进行智能切片；
        save_snapshot=True 时额外写入 JSON 快照，供下次启动安全重建。
        """
        if not documents:
            logger.warning("[KB] 没有文档可处理")
            return None
        
        try:
            # 使用 RecursiveCharacterTextSplitter 进行文档切片
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                length_function=len,
                separators=["\n\n", "\n", "。", "，", " ", ""]
            )
            
            split_docs = text_splitter.split_documents(documents)
            logger.info(f"[KB] 文档切片完成: {len(documents)} 个原始文档 -> {len(split_docs)} 个文本块")
            
            if not split_docs:
                logger.warning("[KB] 切片后没有文本块")
                return None
            
            # 创建向量存储（同步阻塞，放入线程池）
            vector_store = await asyncio.to_thread(
                FAISS.from_documents, split_docs, self.embeddings
            )
            logger.info(f"[KB] 向量存储创建成功，包含 {len(split_docs)} 个向量")

            # 写入安全快照（纯 JSON），下次启动无需 pickle 反序列化
            if save_snapshot:
                await asyncio.to_thread(self._write_documents_snapshot, split_docs)

            return vector_store
            
        except Exception as e:
            logger.error(f"[KB] 创建向量存储失败: {e}")
            return None
    
    async def initialize(self) -> bool:
        """
        初始化知识库（延迟加载）

        返回值：
            bool: 初始化是否成功（无论成功与否都不抛异常）
        """
        if self._initialized:
            return True

        async with self._lock:
            if self._initialized:
                return True

            try:
                # 步骤 1：初始化 Embedding 模型（本地 Ollama bge-m3）
                logger.info(f"[KB] 初始化 Embedding 模型: {settings.embedding_model}")

                # 使用本地 OllamaEmbeddings 替代智谱
                self.embeddings = OllamaEmbeddings(
                    model=settings.embedding_model,
                    base_url=settings.ollama_base_url,
                )

                # 步骤 2：确保知识库目录和默认文档
                kb_path = self._ensure_knowledge_base_dir()

                # 步骤 3：优先读取安全 JSON 快照，避免依赖 pickle 反序列化。
                # 开发环境仍允许读取旧的 FAISS 本地索引（便于本地调试）。
                snapshot_docs = self._read_documents_snapshot()
                if snapshot_docs:
                    self.vector_store = await self._create_vector_store_from_documents(
                        snapshot_docs, save_snapshot=False
                    )
                    if self.vector_store is not None:
                        self._initialized = True
                        logger.info("[KB] 已从 JSON 快照重建向量库（无需危险反序列化）")
                        return True
                    logger.warning("[KB] JSON 快照重建失败，回退到本地文档重建")

                allow_dangerous = settings.environment.lower() == "development"
                if allow_dangerous:
                    try:
                        logger.warning(
                            "[KB] FAISS allow_dangerous_deserialization is enabled — do NOT use in production"
                        )
                        self.vector_store = await asyncio.to_thread(
                            FAISS.load_local,
                            settings.vector_store_path,
                            self.embeddings,
                            allow_dangerous_deserialization=True,
                        )
                        logger.info("[KB] 已有向量库加载成功（development 模式）")
                        self._initialized = True
                        return True
                    except Exception as e:
                        logger.info(f"[KB] 未找到现有向量库或加载失败: {e}")
                        logger.info("[KB] 将从本地文档重新创建...")
                else:
                    # 生产环境：绝不打开 pickle 反序列化。
                    # 未读取到 JSON 快照时直接从源文档重建索引。
                    logger.info("[KB] Production mode: skip pickle index, rebuild from knowledge_base")

                # 步骤 4：从本地文档创建向量库
                documents = self._load_documents_from_directory(kb_path)

                if not documents:
                    logger.warning("[KB] 未找到任何文档，将使用默认汽车知识库")
                    if settings.environment.lower() != "development":
                        # 生产环境不把默认知识库写成快照，避免掩盖业务数据缺失
                        logger.warning(
                            "[KB] knowledge_base 为空；请挂载业务知识库或运行 scripts/build_vector_store.py"
                        )
                    # 使用文本切片后统一走 _create_vector_store_from_documents
                    from langchain_text_splitters import RecursiveCharacterTextSplitter

                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=500,
                        chunk_overlap=50,
                        length_function=len,
                        separators=["\n\n", "\n", "。", "，", " ", ""],
                    )
                    documents = splitter.create_documents(
                        [DEFAULT_KNOWLEDGE_BASE],
                        metadatas=[{"source": "default_knowledge_base.md"}],
                    )

                self.vector_store = await self._create_vector_store_from_documents(
                    documents, save_snapshot=True
                )

                # ═══ 最终检查：确保初始化成功后向量库必须存在 ═══
                if self.vector_store is None:
                    logger.error("[KB] 初始化流程完成但向量库为 None，标记为失败")
                    self._init_error = "初始化后向量库仍为 None"
                    self._initialized = False
                    return False

                self._initialized = True
                return True

            except Exception as e:
                self._init_error = str(e)
                logger.error(f"[KB] 知识库初始化失败: {e}")
                # 初始化失败不抛异常，设置标志让后续调用知道状态
                self._initialized = False
                return False
    
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        检索相关知识
        
        防御性设计：
        - 未初始化时尝试自动初始化（强制）
        - 检索失败返回空列表而非报错
        - 过滤低相关度结果
        """
        # ═══ 强制初始化检查（修复：确保向量库就绪）═══
        if not self._initialized or self.vector_store is None:
            logger.info("[KB] 向量库未就绪，触发自动初始化...")
            success = await self.initialize()
            if not success:
                logger.warning("[KB] 自动初始化失败，返回空结果")
                return []
            
            # 再次检查向量库是否就绪
            if self.vector_store is None:
                logger.error("[KB] 初始化后向量库仍为 None")
                return []
        
        # 防御性参数校验
        if not query or not isinstance(query, str):
            logger.warning("[KB] 查询为空或类型错误")
            return []
        
        query = query.strip()
        if not query:
            return []
        
        if not self.vector_store:
            logger.warning("[KB] 向量库未就绪")
            return []
        
        try:
            logger.info(f"[KB] 执行检索: query='{query[:50]}...', top_k={top_k}")

            # 执行相似度搜索（FAISS 为同步阻塞调用，放入线程池避免卡住事件循环）
            docs_with_scores = await asyncio.to_thread(
                self.vector_store.similarity_search_with_score,
                query,
                k=top_k
            )

            results = []
            for doc, score in docs_with_scores:
                result = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score),
                    "source": doc.metadata.get("source", "unknown")
                }
                results.append(result)

            # 过滤低相关度结果（平方 L2 距离：阈值见 RELEVANCE_THRESHOLD 说明）
            filtered_results = [r for r in results if r["score"] < RELEVANCE_THRESHOLD]

            logger.info(f"[KB] 检索完成: 原始 {len(results)} 条, 过滤后 {len(filtered_results)} 条")

            return filtered_results

        except Exception as e:
            logger.error(f"[KB] 知识库检索失败: {e}")
            return []
    
    async def add_documents(self, texts: List[str], metadatas: List[Dict] = None) -> bool:
        """
        添加文档到知识库
        
        返回值：bool 表示是否成功
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                return False
        
        if not self.vector_store:
            logger.error("[KB] 向量库未就绪，无法添加文档")
            return False
        
        try:
            await asyncio.to_thread(
                self.vector_store.add_texts, texts, metadatas=metadatas
            )
            # 保存到本地（FAISS 原生格式仅在同一环境下可安全重建）
            try:
                self.vector_store.save_local(settings.vector_store_path)
            except Exception as e:
                # save_local 写入的 index.pkl 在生产环境不会被读取，
                # 因此这里失败不影响 JSON 快照路径
                logger.warning(f"[KB] FAISS 本地保存失败（非阻塞）: {e}")

            # 同步追加到 JSON 快照，保证生产环境下次启动能安全重建
            snapshot = self._read_documents_snapshot() or []
            from langchain_core.documents import Document

            for i, text in enumerate(texts):
                metadata = metadatas[i] if metadatas and i < len(metadatas) and isinstance(metadatas[i], dict) else {}
                snapshot.append(Document(page_content=text, metadata=metadata))
            await asyncio.to_thread(self._write_documents_snapshot, snapshot)

            logger.info(f"[KB] 成功添加 {len(texts)} 个文档到知识库")
            return True
            
        except Exception as e:
            logger.error(f"[KB] 添加文档失败: {e}")
            return False
    
    async def reload_knowledge_base(self) -> bool:
        """重新加载知识库（用于手动刷新）"""
        logger.info("[KB] 开始重新加载知识库...")
        self._initialized = False
        self.vector_store = None
        return await self.initialize()
    
    def get_status(self) -> Dict[str, Any]:
        """获取知识库状态信息"""
        return {
            "initialized": self._initialized,
            "init_error": self._init_error,
            "embedding_model": settings.embedding_model,
            "knowledge_base_path": settings.knowledge_base_path,
            "vector_store_path": settings.vector_store_path,
        }


# ═══════════════════════════════════════════════════════════════
# 全局知识库服务实例
# ═══════════════════════════════════════════════════════════════

kb_service = KnowledgeBaseService()


# ═══════════════════════════════════════════════════════════════
# LangGraph 节点函数
# ═══════════════════════════════════════════════════════════════

async def knowledge_retrieval_node(state: SalesState) -> SalesState:
    """
    知识库检索节点 - 防御性增强版
    
    无论发生任何情况，都返回干净的 state 字典，绝不报错崩溃
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 开始知识库检索")
    
    try:
        # 防御性：确保 knowledge_results 存在
        if "knowledge_results" not in state:
            state["knowledge_results"] = []
        
        # 获取用户查询（防御性处理）
        messages = state.get("messages", [])
        query = ""
        if messages and isinstance(messages, list):
            try:
                last_message = messages[-1]
                query = getattr(last_message, 'content', str(last_message))
            except Exception as e:
                logger.warning(f"[KB Node] 获取用户消息失败: {e}")
                query = "产品信息"  # 默认查询
        
        if not query:
            query = "产品信息"
        
        # 执行检索
        context = state.get("context", {})
        filters = context.get("filters") if isinstance(context, dict) else None
        
        results = await kb_service.search(
            query=query,
            top_k=5,
            filters=filters
        )
        
        # 更新 state
        state["knowledge_results"] = results

        wants_gallery = any(word in query for word in ("图片", "照片", "实拍", "多款", "十款"))
        images = find_car_images(query, context, fallback_to_popular=wants_gallery)
        if not images and results:
            retrieved_text = " ".join(str(item.get("content", "")) for item in results)
            images = find_car_images(
                retrieved_text,
                context,
                max_results=requested_image_count(query),
                fallback_to_popular=wants_gallery,
            )
        state["images"] = images
        logger.info("[KB Node] 匹配车型图片 %s 张", len(images))
        
        if results:
            logger.info(f"[KB Node] 检索到 {len(results)} 条相关知识")
            # 打印检索到的具体内容，便于调试
            for i, result in enumerate(results[:3], 1):  # 只打印前3条
                logger.info(f"[KB Node] [结果 {i}] Source: {result['source']}, Score: {result['score']:.3f}")
                logger.info(f"[KB Node] [结果 {i}] Content: {result['content'][:100]}...")

            # 有知识库结果，进入知识整合节点
            state["next_node"] = "knowledge_synthesis"
        else:
            logger.warning("[KB Node] 未检索到相关知识，使用默认回复")
            # 无结果，直接生成回复（不中断）
            state["next_node"] = "sales_response"
            # 可选：添加默认提示
            state["metadata"] = state.get("metadata", {})
            state["metadata"]["knowledge_hint"] = "未找到匹配的产品信息，将使用通用话术回复"

        return strip_messages(state)

    except Exception as e:
        logger.error(f"[KB Node] 知识库检索节点异常: {e}")
        # 防御性兜底：任何错误都不中断流程
        state["knowledge_results"] = []
        state["error"] = f"知识库检索异常: {str(e)}"  # 记录错误但不阻断
        state["next_node"] = "sales_response"
        state["metadata"] = state.get("metadata", {})
        state["metadata"]["knowledge_fallback"] = True
        return strip_messages(state)


async def knowledge_synthesis_node(state: SalesState) -> SalesState:
    """
    知识整合节点 - 防御性增强版
    
    将检索到的知识与上下文整合，生成回答
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from langchain_openai import ChatOpenAI
    
    session_id = state.get("session_id", "unknown")
    logger.info(f"[Session: {session_id}] 开始知识整合")
    
    try:
        # 防御性：检查知识结果
        knowledge_results = state.get("knowledge_results", [])
        if not knowledge_results or not isinstance(knowledge_results, list):
            logger.warning("[KB Synthesis] 没有知识结果可整合")
            state["next_node"] = "sales_response"
            return strip_messages(state)
        
        # 准备知识上下文
        knowledge_context = "\n\n".join([
            f"[相关度: {r['score']:.3f}] {r['content']}"
            for r in knowledge_results[:3]  # 只取前3条
        ])
        
        # 构建提示
        synthesis_prompt = f"""你是一位专业的丰田汽车销售顾问。基于以下从知识库检索到的信息，回答客户的问题。

检索到的相关信息：
{knowledge_context}

请根据以上信息，为客户提供准确、专业的回答。
如果检索到的信息不足以回答问题，请诚实地告知客户你需要进一步确认。

回答要求：
1. 语言简洁专业，基于检索信息，不编造价格/政策
2. 突出产品优势和价值
3. 回复不超过 300 字
4. 自然收尾，引导客户进行下一步（索取详细资料、预约试驾等）"""

        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.7,
        )
        
        # 获取用户消息
        messages = state.get("messages", [])
        user_content = "请介绍相关产品信息"
        if messages and isinstance(messages, list):
            try:
                user_content = getattr(messages[-1], 'content', user_content)
            except:
                pass
        
        messages = [
            SystemMessage(content=guard_system_prompt(synthesis_prompt)),
            HumanMessage(content=guard_user_content(str(user_content)))
        ]

        response = await llm.ainvoke(messages)
        answer = response.content if hasattr(response, "content") else str(response)

        # 保存到 metadata，供后续节点使用
        state["metadata"] = state.get("metadata", {})
        state["metadata"]["knowledge_response"] = answer
        # 性能修复：知识整合节点直接产出最终回复（避免下游再打一次 LLM）
        state["sales_response"] = answer
        state["suggested_actions"] = ["获取报价", "了解详情", "预约试驾"]
        state["next_node"] = "sales_response"  # 下游节点检测到已有回复直接结束

        logger.info(f"[KB Synthesis] 知识整合完成，生成 {len(answer)} 字符回复")

        from langchain_core.messages import AIMessage

        return {
            "sales_response": answer,
            "suggested_actions": ["获取报价", "了解详情", "预约试驾"],
            "metadata": state["metadata"],
            "messages": [AIMessage(content=answer)],
            "next_node": "sales_response",
        }

    except Exception as e:
        logger.error(f"[KB Synthesis] 知识整合失败: {e}")
        # 防御性兜底
        state["error"] = f"知识整合失败: {str(e)}"
        state["next_node"] = "sales_response"
        return strip_messages(state)


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def get_knowledge_base_status() -> Dict[str, Any]:
    """获取知识库状态（用于健康检查）"""
    return kb_service.get_status()


async def reload_knowledge_base() -> bool:
    """重新加载知识库（管理接口）"""
    return await kb_service.reload_knowledge_base()
