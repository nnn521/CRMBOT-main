# 中国市场官方资料候选清单

> 全部条目均为 **未人工批准（UNAPPROVED）**，仅供资料审核与后续取证，不代表已入库、已发布、已冻结评测集或可直接对客作答。本次只研究来源并新建本文；不下载、打开或解析 PDF，不生成 240 题，不调用业务付费模型 API。

## 取证范围与状态口径

- 市场：中国；车型：凯美瑞、汉兰达、RAV4 荣放，汽油与混动分别记录。
- 研究日期：2026-10-20，时区 Asia/Shanghai（UTC+08:00）。首个本机时间记录为 `2026-10-20T13:35:01+08:00`。早期 WebFetch 未返回逐请求时间，统一记为当日第一轮；RAV4 浏览器/API补证时间为 14:27–14:29，精确时间见相关条目。不虚构逐条秒级时间。
- 方法：WebSearch 只发现 URL；WebFetch 读取 HTML/JSON 原文；对 WebFetch 只有标题的三车页面，补用浏览器读取渲染正文，RAV4另核对实际资源请求及公开 JSON。搜索摘要中的价格、年款、PDF标题均不视为已核实正文。广汽丰田两车浏览器补证时间为14:34–14:35，见补证条目。
- **成功／正文可读**：取得相关 HTML/JSON 正文；**成功／仅标题**：工具返回标题但无足够车型正文，不能视为配置核验成功；**部分可读**：能读导航、脚注，但动态配置表未出现在本次 WebFetch 结果；**未访问**：只发现 URL；**请求失败**：保留工具实际错误，不推断网站离线。
- 除 RAV4 浏览器/API补证明确观测到 HTTP 200 外，WebFetch 的成功不等于已记录 HTTP 状态码；未返回状态码的不填写 200。
- 年款必须是车型相关原文明示的“20XX款”。“第九代／第六代”、发布日期、CSV文件名日期、版权年份、导航中其他车系年款，均不等于该车型年款。没有确认年款的条目不标“当前款／2026款”。
- 候选问答范围是**人工批准、版本冻结之后**可能支持的用途；当前均未授权作为正式知识事实。指导／建议零售价不能当实时成交价、门店优惠、库存或贷款利率。

## 一、官方身份与车型入口

| ID | 精确 URL | 获取时间与访问结果 | 原文证据／年款 | 可用于哪些问答 | 审批状态 |
|---|---|---|---|---|---|
| ROOT-T | <https://www.toyota.com.cn/> | 2026-10-20 第一轮，WebFetch 成功／正文可读 | 标题“丰田中国官方网站 - 首页”；页脚“©2021丰田汽车（中国）投资有限公司 版权所有”。原文提供下列三车官方车型链接；未标三车具体年款 | 官方车型入口、品牌渠道导航；不支持参数或价格 | 未人工批准 |
| ROOT-G | <https://www.gac-toyota.com.cn/> | 同日第一轮，WebFetch 成功／仅标题“广汽丰田” | 本次提取不足以核实车型或运营主体全称；广汽丰田车型域名关联另有 ROOT-T 的官方出站链接支持 | 官网入口导航；不能据此回答配置 | 未人工批准 |
| ROOT-F | <https://www.ftms.com.cn/> | 同日第一轮，WebFetch 成功／仅标题“一汽丰田官网” | 主页本次没有提取出车型链接；不可把搜索无结果视为车型不存在。RAV4 对应关系由 ROOT-T 与 RAV-HTML/API补证 | 官网导航；不支持配置 | 未人工批准 |

ROOT-T 实读原文给出的精确对应关系：

| 车型文字 | 官方出站 URL | 审批状态 |
|---|---|---|
| CAMRY 凯美瑞／CAMRY 凯美瑞 智能电混双擎 | <https://www.gac-toyota.com.cn/vehicles/newcamry> | 未人工批准 |
| HIGHLANDER 汉兰达／HIGHLANDER 汉兰达 智能电混双擎 | <https://www.gac-toyota.com.cn/vehicles/newhighlander> | 未人工批准 |
| RAV4 荣放／RAV4 荣放 智能电混双擎 | <https://www.ftms.com.cn/next/car-type/car-detail/93> | 未人工批准 |

## 二、RAV4 荣放：已追到真实官方配置来源

### RAV-HTML：真实车型页面

- URL：<https://www.ftms.com.cn/next/car-type/car-detail/93>。
- 官方来源链：ROOT-T 官方首页中两种 RAV4 名称均指向此 URL；在该 URL 实际渲染出“全球第六代RAV4荣放”、参数配置表和“一汽丰田汽车销售有限公司版权所有 Copyright 2024 FAW TOYOTA Motor Sales Co.,LTD”。不是根据路径数字或第三方索引猜车型。
- 获取／访问：2026-10-20 第一轮 WebFetch 仅返回“一汽丰田官网”，**配置提取未成功**；浏览器补证成功，主页面请求观测 HTTP 200；14:27:48.834+08:00 记录页面URL、标题“车型详情”和实际请求资源；14:28–14:29 读取参数与说明。
- **年款未明确**。实读名称为“全球第六代RAV4荣放”；正文匹配到代际名称，没有据此填写“2026款”。
- 页面具有“参数配置”“电子型录”“查看产品手册”入口。它们不是普通 `<a href>`，本次直接枚举锚点未得到型录地址；真实下载地址由 RAV-API 中的配置字段给出。
- 可用于问答：车型官方入口、已冻结资料版本的六款车型差异、尺寸、动力、WLTC工况油耗、装备有无、选装色条件等。须保留版本、工况、单位与脚注；不能答未核实年款、实时优惠/库存或实际驾驶油耗承诺。
- 审批：**未人工批准**。

### RAV-API：页面真正使用的公开内容接口

- 精确 URL：<https://os.ftms.com.cn/web-bff/website/api/car/publishedDetail?vehicleId=93>。
- 发现依据：浏览器 `performance.getEntriesByType('resource')` 记录到 RAV-HTML 加载该 URL。不是推测接口。
- 访问：2026-10-20 WebFetch 成功读取 JSON；浏览器同页读取公开接口返回 HTTP 200，并将其名称、配置字段与渲染页面交叉核对。配置补证精确时间 `2026-10-20T06:28:51.901Z`（北京时间 14:28:51.901）。
- 原文根字段：`success`、`code`、`message`、`data`。
- `data.name = 全球第六代RAV4荣放`。
- `data.publishTime = 2026-05-11 17:35:00`：仅记录接口原字符串，**接口未说明时区，也不代表车型年款或活动有效期**。
- `data.paramConfig.configurationTitle = 全球第六代RAV4荣放20260511 v10.csv`：是配置文件标题／修订标识，不是年款证据。
- `data.paramConfig.configurationParameter` 是内嵌 JSON 字符串，解析后有 `hasPrice` 和 `data[]`；每个车型记录有 `name`、`price`、`spec[].catalog`、`spec[].params[].name/txt`。本次配置证据来自该内嵌 JSON 与页面，不是下载 CSV/PDF。
- `data.paramConfig.configurationParameterUrl` 提供 CSV 地址，见 RAV-CSV。
- `data.highLightConfig.ftmsVehicleHighlightTabs` 下的 `highlightStyles` 字符串解析后包含 `brochureUrl`，见 RAV-PDF。
- 可用于问答：适合后续建立可定位的“配置版本 → 参数名 → 参数值”证据；必须冻结接口内容，避免同一 URL 被运营更新后覆盖历史依据。本次未保存或计算原件哈希，因此还不是不可变证据版本。
- 审批：**未人工批准**。

以下为 RAV-API 实读配置的有限摘录，用于证明来源对应关系；不是完整配置表，也不冒充业务已审核答案。六款均列长×宽×高 `4,620×1,855×1,680 mm`、轴距 `2,690 mm`。

| 接口车型名（仅去掉 `<br/>` 排版） | 页面“厂家建议零售价格”对应值（元） | 驱动方式 | WLTC综合工况油耗（L/100km） | 双擎系统最大输出功率（kW） | 审批状态 |
|---|---:|---|---:|---|---|
| 2.0L汽油版 豪华版 | 179800 | 前驱 | 6.29 | `-` | 未人工批准 |
| 2.0L汽油版 四驱豪华版 | 189800 | 适时四轮驱动 | 6.65 | `-` | 未人工批准 |
| 2.0L双擎版 精英版 | 169800 | 前驱 | 4.59 | 144 | 未人工批准 |
| 2.0L双擎版 豪华版 | 187800 | 前驱 | 4.59 | 144 | 未人工批准 |
| 2.5L双擎版 四驱豪华版 | 212800 | E-FOUR电子四驱 | 4.91 | 174 | 未人工批准 |
| 2.5L双擎版 四驱旗舰版 | 228800 | E-FOUR电子四驱 | 5.23 | 174 | 未人工批准 |

核验细节与限制（同属未人工批准）：

- 页面另列“限时焕新价”，不得与“厂家建议零售价格”混用。本次没有核实优惠开始／截止日期、地域、置换或其他资格；不将这组活动数值作为长期官方指导价或当前成交承诺。接口 `latestPolicy` 本次为 `null`，不能据此认定没有活动或没有条件。
- 2.0L双擎版精英版的“多媒体显示屏”为 `●14英寸`，其他五款为 `●15.6英寸`；“PVM全景监控系统（带3D视图）”精英版为 `-`，其他五款为 `●`；“AP智能泊车辅助”仅四驱旗舰版为 `●`，其余为 `-`。这些对应关系取自每款独立 JSON 记录，避免把扁平化网页中省略的符号误当全系标配。
- `remarks` 明确：“‘●’表示有此配置，‘-’表示无此配置”；通信状况不理想时服务可能不可用，详情咨询经销店；铂金白色、岩石灰x极夜黑双拼色加付2000元，铂金白x极夜黑双拼色加付4000元；展示内容仅供参考，具体以实车为准。
- 页面／PDF冲突状态：**尚不能比较**。页面与 JSON 抽查一致；RAV-PDF 未打开，其年款、版本、参数是否与 `v10` 相同均未知。不得标“已验证无冲突”。

### RAV-CSV／RAV-PDF：只记录地址，未取文件

| ID | 精确 URL | 来源证据 | 获取时间／访问状态 | 年款与冲突 | 可用于哪些问答 | 审批状态 |
|---|---|---|---|---|---|---|
| RAV-CSV | <https://operate-static.ftms.com.cn/operate/4e8271d5796d4c6bb7b34b712f7907ce.csv> | RAV-API 的 `configurationParameterUrl`；文件标题为“全球第六代RAV4荣放20260511 v10.csv” | 2026-10-20 14:28，取得 URL；CSV 本体未请求、未下载、未解析 | 年款未知；未比较文件与接口内嵌表 | 后续原件审核／版本冻结候选；目前不新增事实 | 未人工批准 |
| RAV-PDF | <https://operate-static.ftms.com.cn/operate/f381996168d9482a975e336cabb120de.pdf> | RAV-API 的 `highlightStyles` 内 `brochureUrl`，`isDownloadBrochure=true` | 同日14:28，取得 URL；PDF **未请求、未下载、未打开、未解析**，可达性未知 | 年款、页数、文件标题与页面冲突均待解析 | 待人工允许后核验型录；目前不能回答PDF内任何事实 | 未人工批准 |

## 三、凯美瑞 HTML 与配置页候选

| ID | 精确 URL | 获取时间／访问状态 | 已读原文与年款 | 可用于哪些问答／限制 | 审批状态 |
|---|---|---|---|---|---|
| CAM-HTML | <https://www.gac-toyota.com.cn/vehicles/newcamry> | 2026-10-20 第一轮，WebFetch 成功／仅标题“凯美瑞官方网站” | 未取得正文；本轮**年款未核实**。ROOT-T 对应此小写路径 | 官方车型入口；参数、价格和年款需进一步读取 | 未人工批准 |
| CAM-CASE | <https://www.gac-toyota.com.cn/vehicles/newCamry> | 同日第一轮，WebFetch 成功／仅标题 | 基线文档中的大小写变体；未证实与小写地址的内容或重定向完全一致 | 保留已有候选，避免误称已完成配置核验 | 未人工批准 |
| CAM-CAMPAIGN | <https://campaign.gac-toyota.com.cn/minisite/camry/> | 同日第一轮，WebFetch 成功／标题及极少文本 | 提取到“全新第九代凯美瑞”，无明确年款或完整配置；代际不等于年款 | 代际宣传候选；不支持年度版本参数 | 未人工批准 |
| CAM-T20 | <https://www.gac-toyota.com.cn/minisite/Campaigns/newcamrytable?module=20ejyb&source=camryconfig> | 同日第一轮，WebFetch 部分可读 | 标题“凯美瑞配置”；只见“添加对比车型”等，**未取得已选版本参数表**；导航有凯美瑞17.18万元起、混动17.98万元起，标为建议零售价；凯美瑞年款未明确 | 可作为动态配置入口、脚注候选；不能把导航起价归给 URL 暗示的具体版本 | 未人工批准 |
| CAM-T25 | <https://www.gac-toyota.com.cn/minisite/Campaigns/newcamrytable?module=25hgzgb> | 同日第一轮，WebFetch 部分可读 | 同样未呈现版本参数表；脚注提及2.5HQ旗舰版，不等于当前选择版本；年款未明确 | 后续车型比较取证候选；参数未加载前不回答具体版本差异 | 未人工批准 |
| CAM-THE | <https://www.gac-toyota.com.cn/minisite/Campaigns/newcamrytable?module=20hejyb&source=camryconfig> | 同日第一轮请求失败；工具原报 `API Error: Request rejected (429) · Codex: The usage limit has been reached` | **无可用正文**；错误来自工具链，本次不能断言官网返回429或官网不可访问 | 仅保留待重试入口；不作为事实证据 | 未人工批准 |
| CAM-OLD | <https://campaign.gac-toyota.com.cn/vehicles/camryxle/> | 同日第一轮，WebFetch 成功／正文可读 | 标题和主宣传明确“2019款凯美瑞”；有2019年8月31日截止活动、车型与配置链接 | 仅限明确指定2019款的历史问答；不能用于未指定年份的现售配置、价格或金融政策 | 未人工批准 |

CAM-T20／CAM-T25 的原文限制与资源（全部未人工批准）：

- “●”／“-”／“○”／“○A”分别表示配备、未配备、工厂选装、经销店选装。图片与配置展示供参考，以实车为准，配置可能调整。
- 丰云悦享须申请开通，五年免费期限从购车发票日起算，功能依版本配置；48GB流量两年有效，会员等可能另购；手机兼容性及通信覆盖有条件限制。不能只摘“免费五年”而省略条件。
- 原文出现“前：麦弗逊式悬架，后：双叉臂独立悬架”的独立弹层文字，未确认其所属配置版本，暂不作为版本参数证据。
- `/download/configpdf/qrcode/camry.png` 是二维码**图片路径**，不是 PDF URL；本次未扫描解码，不猜其目标。页脚 `record_NO.pdf` 为车机APP备案资料，与车型配置表无关，不纳入车型配置语料。
- CAM-OLD 对应的旧配置相对路径包含 `2017`，而页面明确为2019款，说明**路径年份不能代替正文年款**。旧页面促销截止日期不能用于今天的金融问答。

## 四、汉兰达 HTML 与配置页候选

| ID | 精确 URL | 获取时间／访问状态 | 已读原文与年款 | 可用于哪些问答／限制 | 审批状态 |
|---|---|---|---|---|---|
| HIG-HTML | <https://www.gac-toyota.com.cn/vehicles/newhighlander> | 2026-10-20 第一轮，WebFetch 成功／仅标题“汉兰达官方网站” | 年款、动力与价格正文未取得；ROOT-T 两种动力名称均指向此 URL | 官方车型入口；不能据搜索摘要标2026款 | 未人工批准 |
| HIG-TABLE | <https://www.gac-toyota.com.cn/minisite/Campaigns/newhighlanderTable> | 同日第一轮，WebFetch 部分可读 | 标题“汉兰达配置”；选择区域为“请选择”，具体版本表未呈现。导航标汉兰达28.48万元起、汉兰达智能电混双擎24.98万元起，均为建议零售价；汉兰达年款未明确 | 动态配置入口、服务及选装说明；导航起价不绑定某个具体版本 | 未人工批准 |
| HIG-MOBILE | <https://www.gac-toyota.com.cn/minisite/Campaigns/newhighlanderTable/m?model=hhb> | 同日第一轮，WebFetch 部分可读 | 版本表未取得，不能用 `model=hhb` 推断已读豪华版；返回车型路径 `/vehicles/newhighlander/m`；年款未明确 | 移动端配置入口，后续复核；不支持逐版本对比 | 未人工批准 |

汉兰达配置页原文还说明配备符号、实车优先、配置可能调整，以及丰云悦享开通、免费期、流量与手机兼容性限制；其中具体参数和脚注绑定未完整取得。二维码资源 `/download/configpdf/qrcode/newhighlander.png` 是图片，不等于已得到 PDF 地址。移动端提取到孤立的“运动驾驶模式（185T版）”，没有可靠上下文，不作为汉兰达配置事实。上述观察均**未人工批准**。

## 五、广汽丰田浏览器补证：明确年款与页面直链

本节是初轮 WebFetch 之后的补证，保留前表的访问结果，不把先前的仅标题提取改写成成功读到配置。年款证据仅归属下列实际加载的移动端页面，不能自动套用到旧配置表、PDF、大小写变体或其他活动页。以下条目全部**未人工批准**。

### CAM-RENDER：凯美瑞渲染正文

- 起始 URL：<https://www.gac-toyota.com.cn/vehicles/newcamry>；浏览器实际最终 URL：<https://www.gac-toyota.com.cn/vehicles/newcamry/m/>。
- 浏览器原文补证时间：`2026-10-20T06:34:41.448Z`（北京时间14:34:41.448）。标题“凯美瑞官方网站”，正文明确 **“2027款凯美瑞”**。不是从搜索摘要推断。
- 同一移动端 URL 后续 WebFetch 仍只给“凯美瑞官方网站”，**WebFetch未能复现正文提取**。这说明采集方式不同，并不否定已实读的浏览器文本；后续语料采集需保留渲染方式及版本。
- “配置价格”当前展示的2.0智能电混双擎六版本与建议零售价：2.0HE精英版17.98万元、2.0HGVP豪华版18.98万元、2.0HG尊贵版20.58万元、2.0HSE运动Lite版19.18万元、2.0HS运动版20.78万元、2.0HXS运动Plus版20.98万元。当前没有操作其他动力页签，不把这六款当整个车系全部版本。
- 原文三种动力摘要：2.0L汽油最大功率127kW/6600rpm；2.0L智能电混双擎系统最大输出功率145kW；2.5L智能电混双擎169kW。`WLTC综合工况油耗低至4.2L/100公里`的脚注*2明确对应2.0HE智能电混双擎精英版、2.0HGVP智能电混双擎豪华版，并注明与工信部备案一致，实际油耗随使用环境、驾驶方法、车型版本等变化。不能外推为所有版本或实际道路保证。
- “型录下载”的真实href为 <https://gcloudfile.gac-toyota.com.cn/library/CarComp/Camry.pdf>，大小写按页面原样记录；与搜索候选的 `camry9.pdf`、`download/configpdf/camry.pdf` 不是同一精确URL，不能认为内容相同。**没有访问PDF**。
- 原文“标*为部分车型配备，详情请查阅配置表”，辅助驾驶有运行条件与驾驶员职责限制。宣传功能不可不核对版本便当全系标配。金融文案未核验完整适用条件与有效期，不录为贷款测算事实。
- 页面页脚“Copyright©2026 广汽丰田汽车有限公司 版权所有”；该版权年份不能替代正文车型年款。
- 可用于问答：在版本冻结和人工批准后，回答明确2027款的上述建议零售价、动力选项、限定版本WLTC值与限制；不支持旧PDF的年款判断、完整逐版本装备矩阵、实时成交价或当前金融政策。
- 审批：**未人工批准**。

### HIG-RENDER：汉兰达渲染正文

- 起始 URL：<https://www.gac-toyota.com.cn/vehicles/newhighlander>；浏览器实际最终 URL：<https://www.gac-toyota.com.cn/vehicles/newhighlander/m/>。
- 原文补证时间：`2026-10-20T06:34:56.872Z`（北京时间14:34:56.872）。正文明确 **“2026款汉兰达”**，并出现“全域安全智能中大型SUV”“智能电混双擎、380T动力可选”。不是从搜索摘要推断。
- 同一移动端 URL 后续 WebFetch仍只得到“汉兰达官方网站”，具体配置提取未成功；浏览器这次正文也未呈现完整配置价格矩阵，不据此填补HIG-TABLE的版本参数。
- 这次浏览器正文读取未发现普通锚点中的PDF／型录直链，不代表没有其他动态入口；不猜下载URL。
- 原文说明：铂金珍珠白、赛博金外板色另付2000元，ETC选装另付600元；“标*为部分车型配备”；辅助驾驶受道路、车辆、天气等限制；丰云悦享五年免费、48G两年有效均有开通与版本、发票日期、通信等条件。展示以实车为准。
- 可用于问答：人工批准后，可回答本页明确2026款的定位、动力选项和已读条款；不能从该页面给旧PDF绑定年款，也不能补全座位数、尺寸、油耗、具体版本装备。
- 审批：**未人工批准**。

## 六、广汽丰田 PDF 与手册候选：未打开，不据搜索摘要确认年款

下表中CAM-PDF-LIVE由CAM-RENDER页面直接链接，其余PDF通过搜索发现精确URL；全部**没有请求文件本体、下载、打开或解析，也没有以 HEAD 请求测试可达性**。访问成功栏为“未验证”，不能写“成功获取PDF”。文件名中的 camry／highlander 只用于整理线索，不证明其实际标题、年款、动力、版本、现行有效性或参数。所有 PDF 的页面／PDF 冲突状态均为“待比较”。

| ID | 精确 URL | 发现时间／方式 | 年款是否明确／访问状态 | 可用于哪些问答 | 审批状态 |
|---|---|---|---|---|---|
| CAM-PDF-LIVE | <https://gcloudfile.gac-toyota.com.cn/library/CarComp/Camry.pdf> | 2026-10-20 14:34，CAM-RENDER“型录下载”锚点实读 | 本体未读，年款未知；即使2027款页面所链也不保证PDF同年款；可达性未验证 | 优先核验页面直接所链型录，再对比其他PDF候选 | 未人工批准 |
| CAM-PDF-A | <https://www.gac-toyota.com.cn/download/configpdf/camry.pdf> | 2026-10-20 第一轮 WebSearch | 本体未读，年款未知；可达性未验证 | 仅待解析的凯美瑞规格配置候选，不能答数值 | 未人工批准 |
| CAM-PDF-B | <https://gcloudfile.gac-toyota.com.cn/library/CarComp/camry9.pdf> | 同日第一轮 WebSearch | 本体未读，年款未知；不把文件名9当年款；可达性未验证 | 待核实与第九代页面、CAM-PDF-A的版本关系 | 未人工批准 |
| CAM-PDF-OLD | <https://gcloudfile.gac-toyota.com.cn/library/CarComp/camryxle.pdf> | 同日第一轮 WebSearch | 本体未读，年款未知；不能仅因CAM-OLD为2019款便认定此PDF同年款；可达性未验证 | 历史型录候选，暂不入现售事实 | 未人工批准 |
| HIG-PDF-A | <https://www.gac-toyota.com.cn/download/configpdf/newhighlander.pdf> | 同日第一轮 WebSearch | 本体未读，年款、实际动力及配置未知；可达性未验证 | 后续核验混动／版本配置线索，当前不能作事实证据 | 未人工批准 |
| HIG-PDF-B | <https://www.gac-toyota.com.cn/download/configpdf/380Tnewhighlander.pdf> | 同日第一轮 WebSearch | 本体未读；路径包含380T不等于已核实具体动力参数；可达性未验证 | 待核验380T资料与页面是否匹配 | 未人工批准 |
| HIG-PDF-OLD | <https://www.gac-toyota.com.cn/download/configpdf/highlander.pdf> | 同日第一轮 WebSearch | 本体未读，年款未知；不能把搜索摘要说的旧版参数当原文；可达性未验证 | 新旧PDF区别与历史参数核验候选 | 未人工批准 |
| MANUAL-INDEX | <https://www.gac-toyota.com.cn/buy/shopping/product-manual-download> | 同日第一轮 WebFetch，部分可读 | 取得车型导航，但手册区域未呈现这两车具体下载链接；年款未明确 | 官方手册入口导航；不能声称已获得具体手册 | 未人工批准 |

## 七、冲突、有效期与准入结论

| 项目 | 本次可确认的状态 | 后续审核前禁止的结论 | 审批状态 |
|---|---|---|---|
| 凯美瑞页面／PDF疑似年款不一致 | 浏览器CAM-RENDER正文已明确2027款，WebFetch仅标题；PDF本体全部未读，搜索曾提示其他PDF标签年份不同，但**PDF年份与实际冲突仍未核实** | 不能写成已确认“2027页面对2026PDF”；不把页面所链Camry.pdf与其他PDF候选当成同版；不将内容合并为同一年款 | 未人工批准 |
| 凯美瑞旧活动页 | CAM-OLD正文明确2019款、2019年活动截止日期；和未核实年款的新入口分开记录 | 旧零利率、首付、价格不能当现行政策 | 未人工批准 |
| 汉兰达多份PDF并存 | 已发现三个不同官方域名路径，文件均未读；HIG-TABLE动态参数未加载 | 不凭 `new`／`380T`／摘要认定新旧代次、动力或年款；不能声称三份表无冲突 | 未人工批准 |
| RAV4页面／API | 页面真实加载RAV-API；名称、配置版本、有限参数抽查一致；接口发布字符串与CSV版本标题可记录 | 不把20260511或“全球第六代”当年款；不把观察时间当资料生效时间 | 未人工批准 |
| RAV4页面／PDF／CSV | PDF、CSV本体均未请求，无法比较与API内嵌表一致性 | 不标“PDF已核验”“CSV已下载”或“无冲突” | 未人工批准 |
| 价格与有效期 | RAV4厂家建议价与限时焕新价为不同字段；广汽表格页面只读到导航起价。除CAM-OLD过期日期外，本轮未核实各现行页面活动期限 | 不当实时成交、现金优惠、官方利率或门店库存承诺；抓取成功不代表活动持续有效 | 未人工批准 |

人工审核／后续取证仍需完成：确认每份原件实际年款与市场、具体版本、发布日期／生效与失效条件；保存可复核的版本及哈希；核对页面、接口、PDF、CSV之间的差异；由业务人员逐项批准或否决。本轮没有执行这些准入动作。

## 八、检索记录与排除范围

- 核心搜索使用正确限定语法：`site:ftms.com.cn RAV4 荣放`、`site:ftms.com.cn 荣放 filetype:pdf`、`site:ftms.com.cn "荣放" "配置表"`、`site:gac-toyota.com.cn 凯美瑞 Table 配置`。FTMS 搜索覆盖不足，不等于官网不存在；真实RAV4来源通过官方首页出站链接与实际网页请求解决。
- 早期未带冒号的 `site.ftms.com.cn ...`／`site.gac-toyota.com.cn ...` 结果含第三方，未作为官方域名限定结果；后续已更正检索语法。
- 搜索出现汽车之家、爱卡、太平洋、转载PDF、SEO站点及供应商公告等线索，均未纳入官方参数来源；没有把第三方报价当官方价格，也未下载第三方PDF。
- 一条后续WebFetch发生工具链429错误，已在CAM-THE按原报记录。没有把这次失败覆盖为其他已成功页面的状态，也没有把失败推断成官网不可访问。
- 本次没有调用DeepSeek、OpenAI或其他业务付费LLM API，没有触发知识编译／评测，没有编造240条问题；WebSearch/WebFetch仅用于本轮资料检索和网页读取。

## Sources（本次实际采用的官方入口与资料线索）

- [丰田中国官网：三车官方出站入口](https://www.toyota.com.cn/)
- [一汽丰田 RAV4 真实车型页面](https://www.ftms.com.cn/next/car-type/car-detail/93)
- [RAV4 页面实际调用的公开JSON](https://os.ftms.com.cn/web-bff/website/api/car/publishedDetail?vehicleId=93)
- [凯美瑞官方车型入口](https://www.gac-toyota.com.cn/vehicles/newcamry)
- [凯美瑞配置入口](https://www.gac-toyota.com.cn/minisite/Campaigns/newcamrytable?module=20ejyb&source=camryconfig)
- [明确2019款的凯美瑞历史页面](https://campaign.gac-toyota.com.cn/vehicles/camryxle/)
- [汉兰达官方车型入口](https://www.gac-toyota.com.cn/vehicles/newhighlander)
- [汉兰达配置入口](https://www.gac-toyota.com.cn/minisite/Campaigns/newhighlanderTable)
- PDF／CSV全部精确地址及“未访问”状态见上表；列为Sources不表示已读文件。
