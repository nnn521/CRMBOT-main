# RAG v2 实施基线

记录日期：2026-10-20。状态：基础实施开始，真实模型质量与延迟尚未验收。

## 已确认需求

- 当前 Windows 电脑运行数据库与检索，DeepSeek 官方 API 回答和编译 Wiki。
- 本次新增 API 消费上限人民币 50 元；密钥由用户在本机配置，不写入仓库或报告。模型价格和具体型号需真实调用前核实。
- 官方资料范围：中国市场凯美瑞、汉兰达、RAV4 荣放。型号、年款、获取日期、有效期分别记录；不假定官网所有链接代表同一年款。
- 首版共享知识库供所有已登录用户查询；管理员负责上传、审核、发布、撤回。
- 工具提供官方事实查询与明确条件测算，保留外部业务接口；没有真实优惠/库存数据时标记未接入，不使用模拟数据作答。

## 运行资源与已有测试

- Windows 11，本机逻辑处理器 20，物理内存约 16GB。
- NVIDIA GeForce RTX 4070 Laptop GPU，nvidia-smi 报告 8188 MiB 显存。
- Docker Engine 已验证可用；独立 `crmbot-rag-v2` 项目（pgvector 0.8.0-pg16 + Ollama）已启动，未触碰其他项目容器。
- 本地 bge-m3 已从官方分发下载并校验后导入，`/api/embed` 实测 1024 维、单位长度。
- 后端基线：`python -m pytest backend/tests -q`，67 passed，9.08s（改动前）。当前完整回归 633 passed / 3 skipped。
- 真实数据库隔离集成（storage + API/worker + Wiki 任务）：70 passed，临时容器已清理。
- 一次性端到端冒烟（测试文案，非官方资料）：迁移→上传→构建→发布→提问→1 条引用，answer_status=answered，约 5.9s（含建库与构建）。
- 前端：`npm run typecheck` 通过；消息/知识页契约测试 11 passed。
- 当前分支 fix/p0-auth-docs-flow-kb，有既存前端及根文件修改；实施不得覆盖或批量提交无关修改。

## 未完成的基线项

- 官方语料只有最小候选快照（凯美瑞 2027、汉兰达 2026、RAV4 年款未明确），全部未人工审核、未发布；PDF 未解析。
- 评测只有 31 条开发候选，240 条人工集与留出集未建立，不能声称达标。
- 真实检索/回答质量、并发与 p95 延迟尚未评测；端到端冒烟只证明链路可运行。
- Wiki 编译、重排、业务工具接口已有代码与单元/隔离测试，但未接入真实审核 UI 和真实业务系统。
- 综合回答模式为结构性引用校验，未经人工语义评审。

只有完成以上项后，才能声称质量或延迟相对基线改善；回归通过不替代上述验收。

## 官方来源候选（待取证，不自动发布）

- 凯美瑞车型页：https://www.gac-toyota.com.cn/vehicles/newCamry
- 凯美瑞配置表：https://www.gac-toyota.com.cn/download/configpdf/camry.pdf
- 汉兰达混动配置表：https://www.gac-toyota.com.cn/download/configpdf/newhighlander.pdf
- 汉兰达旧版配置表：https://www.gac-toyota.com.cn/download/configpdf/highlander.pdf
- RAV4：尚未获得可核验的正式配置表，继续查找；不得用其他车型结果替代。

搜索结果提示凯美瑞页面/配置表存在年款差异，汉兰达有新旧动力版本。此处仅记录候选 URL，不将搜索摘要作为已审核事实。
