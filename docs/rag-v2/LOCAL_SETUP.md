# RAG v2 Windows 本地基础设施

适用环境：Windows 11、16GB 内存、RTX 4070 8GB、Docker Desktop（WSL2 / Linux containers）。答案生成使用 DeepSeek 云端 API，本次新增调用预算上限 **50 CNY**；本地 Ollama 只承担 embedding，不部署大型聊天模型。

本次只提供独立 Compose、无凭证环境模板及本手册。**尚未下载模型、未取得 API 密钥、未启动服务、未运行数据库迁移，也未验证真实检索或回答质量。** 配置解析通过不代表镜像、GPU、迁移、模型或端到端验收通过。

## 1. 隔离与资源

- 独立项目名 `crmbot-rag-v2`，只使用 `backend/docker-compose.rag-v2.yml`。所有命令显式指定 `-f` 和 `--env-file`，不要与已有 Compose 合并，也不要复用已有项目名。
- PostgreSQL 镜像固定为 `pgvector/pgvector:0.8.0-pg16`，容器端口 5432，仅映射到 `127.0.0.1:55432`；可通过 `RAG_V2_POSTGRES_PORT` 改宿主端口，同时更新知识库 DSN。
- 新库 `crmbot_knowledge_v2`，初始化用户 `rag_v2_owner`；默认卷 `crmbot-rag-v2_rag_v2_pgdata`，不挂载旧库、不修改原 `DATABASE_URL`、不自动迁移。数据库创建不等于 `knowledge` schema 已迁移。
- 数据库密码变量必填且无默认值；host/local 认证均为 SCRAM，不配置 `trust`。Compose 的必填插值只能拒绝空值，不能检查密码熵，使用下方生成的 32 字节随机密码。初始化用户是本地迁移 owner，不应直接作为未来生产 API 的最小权限账号。
- 数据库容器上限 2GB / 2 CPU、共享内存 256MB；可选 Ollama 上限 4GB / 4 CPU。建议先给 Docker Desktop/WSL2 约 6–8GB 内存，并根据实测调整，给 Windows 和其他程序保留余量。这些限制不保证吞吐或模型能装入显存。
- 不增加 worker/API 服务。其启动命令、运行时依赖、健康检查、目录挂载和预算接入须与 runtime 接口另行确认。

## 2. 创建仓库外的私有配置

不要读取、复制或覆盖已有真实 `.env`。模板 `backend/.env.rag-v2.example` 的密码、DSN、API key、模型 digest、账本路径为空。不要把填写后的文件放进仓库；现有忽略规则不能保证忽略 `.env.rag-v2` 或 SQLite 账本。本次不修改 `.gitignore`。

从项目根目录的 PowerShell 执行以下命令，会在用户本地应用数据目录创建新文件；已存在则停止，避免覆盖配置。脚本只读取本次新增的无凭证模板，不打印密码或 DSN。

```powershell
$privateRoot = Join-Path $env:LOCALAPPDATA 'CRMBOT/rag-v2'
$privateEnv = Join-Path $privateRoot 'rag-v2.env'
if (Test-Path -LiteralPath $privateEnv) { throw '私有配置已存在，请手动核对，禁止覆盖。' }
New-Item -ItemType Directory -Force -Path $privateRoot | Out-Null
$budgetDir = Join-Path $privateRoot 'budget'
New-Item -ItemType Directory -Force -Path $budgetDir | Out-Null

$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$secretBytes = New-Object byte[] 32
$rng.GetBytes($secretBytes)
$rng.Dispose()
$dbPassword = [BitConverter]::ToString($secretBytes).Replace('-', '').ToLowerInvariant()
$budgetPath = (Join-Path $budgetDir 'deepseek-budget.sqlite3').Replace('\', '/')
$template = Get-Content -LiteralPath '.\backend\.env.rag-v2.example'
$filled = $template | ForEach-Object {
    if ($_ -eq 'RAG_V2_POSTGRES_PASSWORD=') { "RAG_V2_POSTGRES_PASSWORD=$dbPassword" }
    elseif ($_ -eq 'KNOWLEDGE_DATABASE_URL=') { "KNOWLEDGE_DATABASE_URL=postgresql://rag_v2_owner:${dbPassword}@127.0.0.1:55432/crmbot_knowledge_v2" }
    elseif ($_ -eq 'KNOWLEDGE_BUDGET_PATH=') { "KNOWLEDGE_BUDGET_PATH=$budgetPath" }
    else { $_ }
}
[System.IO.File]::WriteAllLines($privateEnv, [string[]]$filled, [System.Text.UTF8Encoding]::new($false))
Remove-Variable dbPassword, secretBytes, filled, template

$composeArgs = @('--env-file', $privateEnv, '-f', '.\backend\docker-compose.rag-v2.yml')
```

用文件属性的“安全”页限制私有目录 ACL，仅允许本人和必要的系统/管理员访问；不要共享、同步到公开云盘、截图或上传这个文件。随机 hex 密码可直接用于 URL；若改用含 `@`、`:`、`/`、`#`、`%` 等字符的密码，DSN 中必须做 URL percent encoding，Compose 的原始密码保持原值。

密钥以后从 [DeepSeek 官方平台](https://platform.deepseek.com/)自行创建，只填入私有文件的 `KNOWLEDGE_API_KEY`，不要写在命令行、聊天、日志、报告或 Git 中。Compose 不会将此 API key 注入 db/Ollama。此模板不配置应用 JWT；未来启动现有 API 时仍须独立安全配置 `SECRET_KEY`（至少 32 字符且非占位值）和原认证项。

## 3. 只检查配置，或在以后显式启动数据库

`--env-file` 只为 Compose 插值提供值，不会把整个文件导出到当前 PowerShell。指定它也避免 Compose 默认寻找项目 `.env`。环境变量的优先级高于文件：请确保当前 shell 未残留其他 `RAG_V2_POSTGRES_PASSWORD` / `RAG_V2_POSTGRES_PORT` 覆盖值；不要通过打印完整环境来检查。

```powershell
# 仅校验，禁止省略 --quiet 打印含密码的 resolved config。
docker compose @composeArgs config --quiet
# 连同可选 profile 校验；不会拉镜像、启动服务或下载模型。
docker compose @composeArgs --profile ollama config --quiet
```

本次交付验证只允许使用临时 dummy 密码环境、显式空 env 文件及 `config --quiet`，不使用上面的真实私有配置。不要把 dummy 密码用于实际启动。

以下是**用户后续准备就绪时**手动执行的操作，本次没有执行。首次 `up` 可能下载容器镜像，但没有模型下载钩子，也没有迁移启动钩子。

```powershell
docker compose @composeArgs up -d db
docker compose @composeArgs ps
```

`pg_isready` 健康检查只表示服务接受连接，不验证迁移或权限。密码只在首次初始化空卷时生效；修改配置不会修改已存在卷内角色密码。遇到认证失败不要删除卷“修复”，应核对端口和目标实例，在备份后按 PostgreSQL 密码轮换流程处理。

## 4. Ollama 二选一，模型必须手动下载

优先使用原生 Windows Ollama，或显式启用 Compose 的 `ollama` profile。两种方式都使用 `http://127.0.0.1:11434`，不能同时占用端口。默认 `up -d db` 不启动 Ollama。

容器方案依赖 Docker Desktop/WSL2 的 NVIDIA GPU 支持，配置 `gpus: all`，需支持该字段的 Compose（2.30+）。`ollama/ollama:latest` 仅供可选本地基础设施使用，其版本会漂移；正式评测前记录实际版本与镜像 digest，并在后续获准调整配置时固定。不要声称当前已测试 GPU 可用。

```powershell
# 仅选容器方案时执行；启动 Ollama 服务，不自动 pull 模型。
docker compose @composeArgs --profile ollama up -d ollama
```

首选基线为 `bge-m3`（1024 维 embedding）。以下下载命令需用户显式选择，可能占用网络、磁盘、内存和显存；本次不执行。不配置 DeepSeek 本地权重、大型聊天模型或额外 reranker。先从小批量、单并发验证 16GB/8GB 实际资源占用。

```powershell
# 原生方案：在已经安装并运行原生 Ollama 后手动执行。
ollama pull bge-m3
# 或者容器方案（二选一）。
docker compose @composeArgs --profile ollama exec ollama ollama pull bge-m3

# 已下载后读取本地模型身份，不会触发下载，也不涉及 API 密钥。
$tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags'
$tags.models | Select-Object name, digest
```

将对应模型的**完整 `sha256:...` digest**填入私有配置 `KNOWLEDGE_EMBEDDING_REVISION`。模型名、digest、1024 维须与发布清单一致；更换 embedding 必须重建新知识发布版本，不能混合向量。当前尚未下载模型，因此模板不虚构 digest。

## 5. 显式迁移到新库

仅在目标数据库已经启动且确认是上述独立新库后执行。`backend/scripts/migrate_knowledge.py` 仅读取进程环境中的 `KNOWLEDGE_DATABASE_URL`，不读取 `.env`，不回退到业务 `DATABASE_URL`；DSN 必须是 `postgresql://` 或 `postgres://`，不能使用 `postgresql+asyncpg://`。

后续执行迁移前，按下面方式显式把私有文件导入**当前进程**。该解析器适用于模板的简单 `KEY=value` 格式，不执行文件内容；不要加 shell 表达式、引号、行内注释或多行值。它不会显示值。运行时也需显式加载这些变量，不能假定 `.env.rag-v2.example` 被应用自动发现。

```powershell
Get-Content -LiteralPath $privateEnv | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}

# 项目根目录；使用已安装 backend 精确锁定依赖的 Python 环境。
# 沙盒依赖布局才需要 PYTHONPATH=.../backend/pylib；普通虚拟环境不用。
python .\backend\scripts\migrate_knowledge.py --list
# --list 只列出本地迁移文件与校验和，不连接数据库。
python .\backend\scripts\migrate_knowledge.py --dsn-env KNOWLEDGE_DATABASE_URL
```

迁移 runner 已在 Windows 选择 `SelectorEventLoop`，无需再修改全局 event loop policy。脚本通过事务、advisory lock 和校验和执行 `backend/migrations/knowledge/` 的迁移；扩展/DDL 失败会回滚。它需要目标库角色拥有创建 pgvector 扩展及 knowledge schema 对象的权限，不会由 Compose、API 启动或健康检查自动执行。不要用旧库做试验，不要设置 `TEST_KNOWLEDGE_DATABASE_URL` 指向有价值的数据。

保持 `RAG_V2_ENABLED=false`，直到模型 digest、迁移、授权、runtime 接线和质量验证完成；本手册不提供猜测的 worker/API 启动命令。

## 6. DeepSeek、50 元预算与持久账本

官方资料核验日期：**2026-10-20**。当前官方模型 ID 为 `deepseek-flash`，HTTP JSON 使用 `"thinking": {"type": "disabled"}` 关闭思考；OpenAI SDK 使用 `extra_body` 传递。现有 RAG v2 `DeepSeekClient` 已发送此参数，模板只设 `KNOWLEDGE_ANSWER_MODEL=deepseek-flash`，不修改旧 `DEFAULT_MODEL` 或代码里的旧默认模型。

- [官方人民币价格表](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)：高峰、缓存未命中输入 **2 CNY / 百万 token**，输出 **8 CNY / 百万 token**。按该上界预留，不预支缓存/低谷优惠；实际调用前重新核价，有上涨则先更新配置。核验日期不是官方页面更新时间。
- [官方思考模式参数](https://api-docs.deepseek.com/guides/thinking_mode)。模型名和参数不能据旧教程推断。
- `KNOWLEDGE_BUDGET_CNY=50`；`KNOWLEDGE_INPUT_PER_MILLION_CNY=2`、`KNOWLEDGE_OUTPUT_PER_MILLION_CNY=8`。不自动充值或获得额度，不调用 API 检查 key。
- `KNOWLEDGE_BUDGET_PATH` 必须指向仓库外绝对路径的持久 SQLite 文件（上方脚本已设置）。runtime 当前支持该路径，账本会创建父目录；本次不创建账本或产生调用。将目录及 SQLite 配套文件纳入私有备份，不放临时目录、容器可写层、OneDrive 或网络盘。
- 所有受此次 50 元授权约束的知识调用共用**同一个**账本；保留其记录贯穿重启、升级和试验。禁止删除、更换路径、清空账本或提高预算来绕过上限；未来容器化 worker/API 时需挂载同一持久目录并统一路径。
- 当前账本先预留后调用，用 SQLite 事务协调本机多进程；网络错误、缺失 usage 等不确定情况保留预留，不自动付费重试；已计费但 JSON 无效仍记账。账本不是供应商余额，不保证限制其他软件或旧链路支出。
- 旧意图识别、其他 API 客户端或独立程序不一定经过此账本。未来真实试验前核对全部付费调用并在平台侧管理独立 key/额度，不能把本地 50 元账本宣称为全账户硬限额。另见 [评测与预算规范](EVALUATION_GUIDE.md)。

## 7. 停止与验收状态

准备停止时使用相同文件和独立项目；`down` 不带 `-v`，保留新数据库与模型卷。切勿对旧 Compose 项目执行这些命令。

```powershell
docker compose @composeArgs --profile ollama down
# 不执行 down -v、volume prune 或旧数据库卷操作。
# 不再需要当前 shell 的密钥时，清除进程副本；私有文件仍需妥善保存。
Remove-Item Env:KNOWLEDGE_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:KNOWLEDGE_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:RAG_V2_POSTGRES_PASSWORD -ErrorAction SilentlyContinue
```

提交时仅包含本次三个无凭证文件；不提交私有 env、API key、DSN、账本、数据库导出或模型文件。本次没有执行 commit。

待后续实际操作验证的项目包括：镜像启动和端口、SCRAM 认证、pgvector 版本、显式迁移、GPU 与 embedding digest、预算持久化、真实检索/回答及人工质量评审。**当前没有真实质量结论，也没有通过本手册承诺性能指标。**
