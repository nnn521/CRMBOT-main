# RAG v2 评测状态

状态：仅有 **有限开发候选样本**；正式 240 条人工审核集、留出集和真实检索/模型验收均未完成。本文不宣称质量、延迟或成本改善，也不宣称任何来源已人工批准或已发布。

## 现有文件

| 文件 | 性质 | 数量／状态 |
|---|---|---|
| `docs/rag-v2/evaluation/development.jsonl` | 离线开发候选样本；JSONL，一行一题 | 31 题，18 正例／13 负例；全部 `review_status=candidate`、`approval_status=unapproved` |
| `docs/rag-v2/source-snapshot-index.json` | 候选来源索引、gold span 原文定位与哈希、工具契约定位 | 5 个来源、22 个 span；`status=candidate` |
| 本文件 | 数据状态、限制、复现和转换说明 | 非验收报告 |

数据集 SHA-256：`cbedbb18f9b4b388ef0d12f058ccc017911559ed28c1acb3cf8a5822fb4da7a6`。索引 SHA-256：`03af395f9e083b3d52d81a1df60df9485cb972fa7f6eb34ac78ac03e9bed77a3`。生成后已从已保存的官方字节重新推导全部 22 个 span 的原文摘录，逐一匹配引用哈希；5 个来源原件哈希也与 manifest 一致；并检查所有正例 gold 均未跨车型。

## 覆盖范围（有限，不是 240 题库）

| 类别 | 题数 | 说明 |
|---|---:|---|
| `official_fact` | 8 | 凯美瑞／汉兰达明确年款与已读官方文本；RAV4 名称、尺寸、WLTC、驱动/功率、屏幕 |
| `version_condition` | 8 | 选装、脚注适用版本、标星装备、PVM/AP 版本差异、汉兰达服务与辅助驾驶限制 |
| `model_clarification` | 2 | 未指定车型或同车多个同名版本 |
| `year_clarification` | 2 | 未给年款/动力且快照无法唯一回答 |
| `no_answer` | 4 | RAV4 年款不可确认、未保存旧年款、汉兰达完整矩阵缺失、PDF 未读 |
| `activity_limit` | 2 | 限时价与金融宣传的期限/地域/资格未核实 |
| `tool_explicit_loan` | 3 | 两题明确用户条件测算 + 一题缺利率/期限应澄清 |
| `business_unconnected` | 2 | 报价/库存业务接口未接入，不能编造或把未知当零 |

每题的 `question_family` 唯一，未用同义改写凑数。正例只使用已保存原文中的具体字段或行段；负例 `gold_span_ids` 为空。负例的“无答案”仅指**本有限候选语料与给定上下文**内不能回答，不代表全网没有其他官方资料。

RAV4 年款仍未明确：JSON 的 `data.name` 是“全球第六代RAV4荣放”，`publishTime=2026-05-11 17:35:00`，配置标题含 `20260511 v10`；这些都不等于“20XX款”，所以相关题目 `model_year=null`。凯美瑞/汉兰达年款仅对实际读到的 2027／2026 移动页正文成立，不能套到未读 PDF、旧配置页或其他年款。

## 与 `tools/evaluate_rag.py` 的 schema 对齐

评测脚本读取的是**整个 JSON 数组**，字段最少需要：

```json
[{"id":"...","category":"...","query":"...","gold_span_ids":["..."],"expected_status":"answered"}]
```

`development.jsonl` 是逐行 JSON，不能直接作为 `--dataset`。当前脚本未修改；如需本地试跑，可显式转换为临时 JSON 数组（不写入发布库，不改原 JSONL）：

```bash
python -I -c 'import json,sys; from pathlib import Path; src,dst=map(Path,sys.argv[1:]); rows=[json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]; dst.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")' docs/rag-v2/evaluation/development.jsonl /tmp/rag-v2-development.array.json
python tools/evaluate_rag.py --dataset /tmp/rag-v2-development.array.json --predictions <预测JSON数组> --release candidate-dev-20261020 --model <已记录模型版本> --output <报告路径>
```

本次没有真实预测文件，因此**没有运行模型或检索评分**。仅用 gold 自身构造的 oracle 预测做了一次 schema 自检，全部指标必然为 1.0；这不是模型结果，不能引用为质量证据。转换后的 JSON 数组已能被脚本加载。脚本不调用模型；缺少预测按失败计；正例无 gold 会被拒绝；负例不进入正样本召回分母。

评测脚本只评证据检索与状态，不判断答案语义正确、引用是否支持结论、价格/库存承诺、权限撤回或真实延迟。`expected_behavior` 是候选答案要点，不能当自动判分标准。

## 工具题说明

`tool_explicit_loan` 的两道正例同时要求读取 RAV4 `price` 字段和按用户明确给出的本金/年利率/期限做等额本息测算。gold 仅锚定官方价格字段；`tool_assertions` 保存输入与预期月供/总还款/总利息，来源标记为用户条件测算，**不是**检索 gold，也不被 `evaluate_rag.py` 评分。预期值按仓库 `calculate_loan` 的 Decimal 公式独立重算：10万元、0%、12个月为 8333.33／100000.00／0.00；10万元、名义年利率4.8%、36个月为 2988.12／107572.26／7572.26。测算不含手续费、保险、税费等，不代表银行报价或官方利率。

`business_unconnected` 负例对应 `ToolRegistry` 无 `business_api` 时的 `not_connected` 语义；`dev-tool-loan-missing` 缺少年利率和期限，期望先澄清而不是擅自套用利率。

## 来源与引用规则

- 索引 `source_entries` 保存官方 URL、UTC 抓取时间、SHA-256、车型 scope、年款状态及**仓库相对路径**。`.tmp` 是本地、已被 Git 忽略的研究快照，`local_exists_at_generation=true` 只说明生成时存在；它不是长期可用的发布引用，清理后需按同一 SHA-256 重新取得相同字节。
- `gold_spans` 保存来源定位、原文摘录及摘录 SHA-256。以后引用题目时，应以 span ID + 来源 SHA-256 + 定位 + 摘录为候选证据；不得只引用本地绝对路径或仅凭 URL（官网可变）。
- DOM 来源是浏览器 `document.body.innerText` 的规范化文本摘录/快照，不是原始 HTTP/HTML 字节；采集方式和浏览器侧哈希均已记录。RAV4 JSON／CSV 是原样保存的响应字节；CSV 服务器 `Content-Type` 错标为 `image/jpeg`，实读为 UTF-8 CSV。
- 未下载或解析任何 PDF；Camry.pdf、RAV4 brochure、其他配置 PDF 均不能作为本轮事实依据。索引不含密钥、Cookie、授权头或其他 secret。
- 所有题目与 span 均为 `candidate`／`unapproved`，未写入发布库，不能当人工审核、正式留出集或业务验收。

## 未完成项（不得省略）

1. **正式 240 题人工集**尚未创建：需业务逐题审核问题、gold、期望行为、年款/市场/配置范围和必要历史，并冻结开发/留出划分；当前 31 题只是开发候选，不是 160 开发集，也不是 80 留出集。
2. 当前数据没有 holdout，`split=development`、`is_holdout=false`；不得把本文件或这些题目冒充留出集。
3. 官方来源仍需人工批准；RAV4 年款、凯美瑞页面与 PDF 跨年款关系、汉兰达完整配置矩阵和活动有效期均待核实。
4. 尚无真实检索预测、模型回答、延迟、并发和成本验收；本次未调用付费 LLM，也未修改 app 或发布任何知识。
