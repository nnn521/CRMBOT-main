# RAG v2 评测数据与运行规范

状态：评测程序已实现；正式官方资料集及人工复核题目尚未冻结。不以示例或自动生成题冒充业务验收。

## 输入

`tools/evaluate_rag.py` 仅读取两个 JSON 数组，不调用模型，也不会自动采集或发送资料。

题目记录：

```json
{
  "id": "unique-question-id",
  "category": "exact_model",
  "query": "待业务审核的问题",
  "gold_span_ids": ["immutable-source-span-id"],
  "expected_status": "answered"
}
```

预测记录：

```json
{
  "id": "unique-question-id",
  "candidate_span_ids": ["span-a", "span-b"],
  "ranked_span_ids": ["span-b", "span-a"],
  "context_span_ids": ["span-b", "span-a"],
  "answer_status": "answered"
}
```

原始 span 定位固定到文档版本；多个块关联同一 span 时去重。无答案/歧义题 gold_span_ids 为空且 expected_status 为 clarification/unavailable，不进入正样本召回分母。多证据题同时检查 context 中必要证据是否齐全。缺失预测按失败计，未知/重复 ID 报错而非静默忽略。

从项目根目录执行（使用真实产物路径替换占位路径）：

```bash
python tools/evaluate_rag.py --dataset path/to/cases.json --predictions path/to/predictions.json --release RELEASE_ID --model MODEL_REVISION --output path/to/report.json
```

## 数据准备与审核

总量 240 条，开发 160/留出 80，按车型/来源/问题家族分组划分；人工检查每题证据与期望行为。必须记录市场、年款、配置、参考日期、必要历史、身份、禁止结论。官方页面与 PDF 年款不一致时分别标注。不得将指导价标成实时成交价、库存或官方贷款利率。

真实答案正确性、引用是否支持结论、价格/库存承诺、权限撤回与模型延迟不由此脚本判定，需要另行测试与业务复核。该程序的单元测试不是正式 240 题验收结果。

## DeepSeek 预算与调用约束

- 用户授权本次新增 API 费用上限 50 元人民币。
- model_client.py 固定官方 API 地址，只发送明确提供给它的资料；输入/输出有上限，非思考模式，无自动付费重试。
- budget.py 使用 SQLite BEGIN IMMEDIATE 进行进程间额度预留，账本存持久目录，不能删除账本以重置额度。
- 价格必须配置为核验后的上界；目前官方 Flash 价格核验：未命中输入最高 2 元/百万 token，输出最高 8 元/百万 token（2026-10-20）。缓存优惠不提前计入预算。
- 未拿到 usage 或网络失败保留预留；已计费但 JSON 无效仍记账。超出预留的供应商用量触发异常并要求检查，不自动继续。
- 本预算仅覆盖通过该适配器发起的调用，不能声称限制了其他程序或现有旧链路的消费。正式新路径必须全部接入预算适配器。
- 不把密钥写入报告，不打印完整配置或 HTTP 授权头。

官方资料：
- https://api-docs.deepseek.com/zh-cn/quick_start/pricing
- https://api-docs.deepseek.com/guides/thinking_mode
