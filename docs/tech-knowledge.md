# Web 全栈技术知识文档

> 写给大数据专业本科生（公子）的 Web 全栈技术入门手册。以 CordysCRM（飞致云开源 CRM）和 CRMBOT 两个真实项目为案例，讲清楚「是什么 → 为什么需要 → 在项目里长什么样」。

---

## 第一部分：前端工程化概念

### 1. 路由（Router）

#### 是什么

路由，简单说就是「URL 和页面之间的映射关系」。你在浏览器地址栏输入 `/customers`，看到客户列表页；输入 `/customers/42`，看到编号 42 的客户详情——这就是路由在工作。

**前端路由**与**后端路由**有本质区别：

| | 前端路由（SPA） | 后端路由（传统多页） |
|---|---|---|
| 谁在处理 | 浏览器里的 JS | 服务器 |
| 切换页面时 | 不刷新，替换 DOM | 整页刷新，白屏等待 |
| 典型实现 | Vue Router / React Router | Express / Spring MVC 的 `@RequestMapping` |

**SPA（Single Page Application，单页应用）原理**：浏览器只加载一次 HTML + JS + CSS，之后所有的「页面跳转」其实都是 JS 在本地切换组件、修改 URL hash 或用 History API 操作地址栏——不发生真正的 HTTP 请求。用户感觉很快，因为不需要重新下载整页资源。

```
传统多页应用：
  用户点击链接 → 浏览器发起 GET /about → 服务器返回完整 HTML → 白屏 → 渲染

SPA 单页应用：
  用户点击链接 → Vue Router 拦截 → 替换 <router-view> 里的组件 → 无白屏 → 瞬间完成
```

#### 为什么需要

1. **用户体验**：页面切换瞬间完成，没有白屏闪烁
2. **前后端分离**：前端只关心页面渲染，后端只提供 JSON API，各司其职
3. **代码组织**：路由天然帮你把页面拆成独立模块，维护方便

#### 在项目中的体现

**Vue Router（CordysCRM 使用）**：

```typescript
// CordysCRM 的路由配置简例
const routes = [
  {
    path: '/crm',
    component: DefaultLayout,
    children: [
      { path: 'customer', component: () => import('@/views/customer/index.vue') },
      { path: 'contract', component: () => import('@/views/contract/index.vue') },
    ]
  },
  {
    path: '/login',
    component: () => import('@/views/login/index.vue'),  // 登录页不用 layout
  }
]
```

- `path` 匹配 URL，`component` 指定渲染哪个 .vue 文件
- 嵌套路由（`children`）：外层是布局组件，内层是业务页面
- 懒加载（`() => import(...)`）：只有用户访问时才下载该页面的 JS 代码，首屏更快

**React Router（CRMBOT 未来可能使用）**：

```tsx
// React Router v6 风格
<Routes>
  <Route path="/" element={<ChatLayout />}>
    <Route index element={<ChatView />} />
    <Route path="documents" element={<DocumentsView />} />
  </Route>
</Routes>
```

**CRMBOT 当前状况**：CRMBOT 当前只有 `App.tsx` 一个聊天界面，没有路由。未来如果加后台管理页面（比如文档管理、合同模板管理），就必然需要引入 React Router。

---

### 2. Monorepo

#### 是什么

Monorepo（单体仓库）是把多个相关项目（包）放在**同一个 Git 仓库**里管理。与之相对的是 Polyrepo（多仓库），每个包独立一个 Git 仓库。

**pnpm workspace** 是 pnpm 包管理器提供的 monorepo 工具。它通过根目录的 `pnpm-workspace.yaml` 声明哪些目录是「子包」，然后：

- 子包之间可以**互相引用**（`import { xxx } from '@crm/shared'`）
- 公共依赖**提升到根目录**，避免重复安装（节省磁盘，安装更快）
- 统一命令：`pnpm -r build` 会递归构建所有子包

#### 为什么需要

1. **代码复用**：公共代码写一份，多个子项目共享——不用 copy/paste
2. **统一管理**：版本号、依赖、构建脚本、lint 规则全部统一，不会出现「A 项目用 Vue 3.2、B 项目用 Vue 3.5」这种混乱
3. **原子提交**：改一个公共库的 API，可以同时更新所有调用方，一次 commit 搞定

#### 在项目中的体现

**CordysCRM 的 Monorepo 结构**：

```
frontend/
├── pnpm-workspace.yaml       # 声明 workspace
├── package.json               # 根 package.json（公共脚本）
└── packages/
    ├── lib-shared/            # 🔑 公共库（被 web 和 mobile 依赖）
    │   ├── api/               #   统一的 API 请求封装
    │   ├── assets/            #   公共图片/图标
    │   ├── enums/             #   公共枚举常量
    │   ├── hooks/             #   公共 composable（如 useTable）
    │   ├── locale/            #   国际化语言包
    │   ├── method/            #   工具函数
    │   ├── models/            #   数据模型/类型定义
    │   └── types/             #   TypeScript 类型
    ├── web/                   # PC 端（Vue3 + Naive-UI）
    └── mobile/                # 移动端
```

`lib-shared` 是这套架构的灵魂。`web` 和 `mobile` 都通过 `import { useTable } from '@crm/shared'` 引用公共代码。好处很明显：`useTable` 这个表格逻辑改一次，PC 端和移动端同时生效。

**CRMBOT 当前状况**：

```
crmbot/
├── backend/          # FastAPI + LangGraph（Python）
├── frontend/         # React 19 + Vite（单应用，没有 monorepo）
└── docker-compose.yml
```

CRMBOT 还是**单应用结构**。因为目前只有一个聊天前端，没有移动端、没有管理后台——单应用足够。但如果未来要加 H5 移动版 + 后台管理面板，就会发现「聊天消息类型定义」「API 请求封装」这些代码要在三个地方复制——这时就该考虑引入 monorepo 了。

**总结**：Monorepo 不是银弹。项目简单时（如 CRMBOT 当前）用单仓库就好；当你有多个前端项目需要共享代码时（如 CordysCRM 的 PC + 移动端），monorepo 的价值就体现出来了。

---

### 3. 布局系统（Layout）

#### 是什么

布局系统是前端应用的「骨架」——它规定了页面有哪些固定的区域（顶栏、侧边栏、内容区），以及不同页面如何在这些区域中呈现。

**经典的管理后台布局**：

```
┌──────────────────────────────────────────────┐
│  顶栏（Header）：Logo + 用户头像 + 通知图标    │
├────────┬─────────────────────────────────────┤
│ 侧边栏  │                                      │
│ (Sidebar)│         内容区（Content）             │
│  - 菜单1 │        <router-view />              │
│  - 菜单2 │        实际的业务页面放这里            │
│  - 菜单3 │                                      │
│         │                                      │
└────────┴─────────────────────────────────────┘
```

**default-layout**：带侧边栏 + 顶栏的常规布局，99% 的后台页面用这个。

**full-page-layout**：全屏布局，没有侧边栏和顶栏。适合登录页、大屏展示页——这些页面不需要导航框架。

#### 为什么需要

1. **一致性**：所有页面用同一套壳，切换页面时只有内容区变化，用户不会迷失
2. **复用**：侧边栏菜单、顶栏用户信息、面包屑导航——写一次，所有页面自动继承
3. **按需选择**：登录页不需要侧边栏 → 用 `full-page-layout`；客户列表需要导航 → 用 `default-layout`

#### 在项目中的体现

**CordysCRM 的设计**：

```vue
<!-- DefaultLayout.vue 简化版 -->
<template>
  <n-layout>
    <n-layout-header> <!-- 顶栏 --> </n-layout-header>
    <n-layout has-sider>
      <n-layout-sider> <!-- 侧边栏菜单 --> </n-layout-sider>
      <n-layout-content>
        <router-view />  <!-- 👈 这里放业务页面 -->
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>
```

路由配置中指定哪个页面用哪种布局：

```typescript
{ path: '/login', component: FullPageLayout }        // 登录页，全屏
{ path: '/crm', component: DefaultLayout, children: [...] }  // 业务页，带侧边栏
```

**CRMBOT 当前状况**：

CRMBOT 目前只有一个 `App.tsx`，没有布局系统：

```tsx
// 伪代码：CRMBOT 当前的 App.tsx
function App() {
  return (
    <div className="chat-container">
      <ChatPanel />      {/* 整个页面就是一个聊天窗口 */}
    </div>
  )
}
```

未来如果要加**后台管理**（比如文档列表、合同模板管理），就需要引入布局系统。预期结构：

```
/chat          → ChatLayout（聊天界面，可能没有传统侧边栏）
/admin/docs    → AdminLayout（后台布局，带侧边栏 + 顶栏）
/admin/templates → AdminLayout
/login         → FullPageLayout（登录页）
```

---

## 第二部分：CordysCRM 技术栈

### 1. 整体技术栈

#### 是什么

CordysCRM 是飞致云（FIT2CLOUD）开源的客户关系管理系统，技术栈如下：

```
┌─────────────────────────────────────────────────┐
│                     前端                         │
│  Vue 3 + Vite + TypeScript + Naive-UI + pnpm    │
│  Monorepo: lib-shared / web / mobile             │
├─────────────────────────────────────────────────┤
│                     后端                         │
│  Java + Spring Boot + MyBatis + Shiro            │
│  数据库：MySQL + Redis + Flyway（数据库迁移）      │
│  服务器：Jetty（嵌入式）                          │
├─────────────────────────────────────────────────┤
│                   AI 能力                        │
│  MCP Server（端口 8082，18 个工具）               │
│  Agent 智能体管理模块                             │
└─────────────────────────────────────────────────┘
```

逐层解释：

- **Spring Boot**：Java 生态最流行的 Web 框架，自动配置、内嵌服务器，省去繁琐的 XML 配置
- **MyBatis**：SQL 映射框架，写 SQL 而不是用 ORM 自动生成——适合复杂查询场景
- **Apache Shiro**：权限安全框架，管理「谁能访问什么」
- **MySQL**：关系型数据库，存客户、合同等结构化数据
- **Redis**：内存缓存，存 Session、临时 Token、高频查询结果
- **Flyway**：数据库版本管理工具——用 SQL 脚本记录每次数据库变更，团队协作时不会出现「你加了一个字段但我本地没有」的问题
- **Jetty**：轻量级 Java Web 服务器，Spring Boot 内嵌，不需要单独安装 Tomcat
- **Vue 3 + Vite**：Vue 3 是前端框架（响应式、组件化），Vite 是构建工具（开发时热更新极快）
- **Naive-UI**：Vue 3 的组件库，提供 Button、Table、Modal 等开箱即用的 UI 组件

#### 为什么需要

这套技术栈是 Java 企业级开发的经典选择：

- Spring Boot + MyBatis 是国产 Java 项目的「标配」，招人容易、社区资源丰富
- Shiro 比 Spring Security 更轻量，适合中小型项目
- Flyway 解决了「数据库 schema 怎么同步」这个团队协作中的经典痛点
- Vue 3 + Naive-UI 比 React + Ant Design 更适合国内中小团队（学习曲线更平缓）

#### 在 CRMBOT 中的对比

CRMBOT 选了完全不同的技术路线：

| | CordysCRM | CRMBOT |
|---|---|---|
| 后端语言 | Java | Python |
| 后端框架 | Spring Boot | FastAPI |
| 前端框架 | Vue 3 | React 19 |
| UI 组件库 | Naive-UI | shadcn/ui + Tailwind |
| 状态管理 | Pinia | Zustand |
| 数据库 | MySQL + MyBatis | （对话系统，尚未需要持久化） |
| AI 集成 | 自己暴露 MCP 工具 | 内置 LangGraph + DeepSeek |

两者的定位不同：CordysCRM 是**传统管理后台 + AI 能力外挂**；CRMBOT 是**AI 原生应用**，用对话代替表单。

---

### 2. MCP 协议

#### 是什么

**MCP（Model Context Protocol）** 是 Anthropic（Claude 的开发商）在 2024 年提出的开放协议。它的核心思想很简单：

> AI 大模型需要一个**统一的方式**来调用外部工具（查数据库、发邮件、读文件），而不是每个 AI 平台各搞一套 API。

MCP 采用 **Client-Server 架构**：

```
┌──────────┐    MCP Protocol    ┌──────────────┐
│ AI Agent │ ◄────────────────► │  MCP Server  │
│ (Client) │   JSON-RPC over    │  (工具提供方) │
│          │   HTTP/stdio       │              │
└──────────┘                    └──────────────┘
                                      │
                              提供工具列表如：
                              - search_customers
                              - create_contract
                              - get_sales_report
```

AI Agent 作为 Client，连接 MCP Server 后：
1. Server 告诉 Client：「我有哪些工具，每个工具需要什么参数」
2. Client（AI）根据用户意图决定调用哪个工具
3. Server 执行工具逻辑，返回结果给 AI
4. AI 把结果整合进回答里

#### 为什么需要

在 MCP 之前，每个 AI 平台有自己的「Function Calling」格式（OpenAI 的、Anthropic 的、Google 的），开发者要写多套适配。MCP 提供了**一个协议、一次开发、到处能用**的标准。

对 CordysCRM 来说，MCP 让它的 CRM 功能从「只能人在浏览器里操作」变成「AI 也能调用」——这就是 AI 智能体的基础设施。

#### 在 CordysCRM 中的体现

CordysCRM 在**端口 8082** 启动了一个 MCP Server，暴露了 **18 个工具**，大致分类：

| 类别 | 工具示例 |
|---|---|
| 客户管理 | `search_customers`、`get_customer_detail` |
| 合同管理 | `create_contract`、`query_contracts` |
| 销售漏斗 | `get_opportunities`、`update_opportunity_stage` |
| 数据分析 | `get_sales_report`、`get_customer_analysis` |

外部 AI Agent（比如 Claude Desktop、或者 CRMBOT 本身）连接到 `localhost:8082`，就能操作 CordysCRM 里的数据。举个例子：

```
用户对 AI 说：「帮我查一下上个月签了多少合同」

AI 内部流程：
1. 理解意图：需要查询合同数据
2. 调用 MCP 工具：query_contracts({ date_range: "2025-05" })
3. MCP Server 查询 MySQL，返回：[{id: 1, amount: 50000}, {id: 2, amount: 30000}]
4. AI 回复：「上个月共签订 2 份合同，总金额 80,000 元」
```

**CRMBOT 与 MCP**：CRMBOT 目前不直接使用 MCP 协议（因为它是纯粹的对话生成系统），但未来如果要集成 CordysCRM 或其他外部系统，MCP 就是天然的桥梁。

---

### 3. 智能体管理（Agent 模块）

#### 是什么

CordysCRM 的 Agent 模块是一个**AI 智能体配置管理界面**，让管理员可以创建、编辑、管理多个 AI 智能体（每个智能体有不同的系统提示词、可调用的工具集、行为策略）。

#### 架构设计

```
┌──────────────────────────────────────────────────┐
│  Agent 管理页面                                    │
│                                                   │
│  ┌──────────┐  ┌────────────────────────────────┐ │
│  │ 左侧      │  │  右侧：Agent 表格                │ │
│  │ 树形目录  │  │  ┌────┬──────┬────┬──────┐     │ │
│  │          │  │  │名称 │ 模型  │状态 │ 操作  │     │ │
│  │ 📁 销售部 │  │  ├────┼──────┼────┼──────┤     │ │
│  │  ├─ 售前  │  │  │售前 │ GPT4 │ 启用│ 编辑  │     │ │
│  │  ├─ 售后  │  │  │售后 │ DSv4 │ 启用│ 编辑  │     │ │
│  │ 📁 市场部 │  │  │营销 │ GPT4 │ 停用│ 编辑  │     │ │
│  │  └─ 营销  │  │  └────┴──────┴────┴──────┘     │ │
│  └──────────┘  └────────────────────────────────┘ │
│                                                   │
│  弹窗（创建/编辑 Agent）：                          │
│  ┌────────────────────────────────────────────┐   │
│  │  Agent 名称: [______________]               │   │
│  │  所属分组:   [销售部/售前  ▾]               │   │
│  │  使用模型:   [DeepSeek V4 ▾]               │   │
│  │  系统提示词: [___________________________]  │   │
│  │             [___________________________]  │   │
│  │  可用工具:   ☑ 查询客户  ☑ 创建合同         │   │
│  │             ☐ 删除客户  ☐ 导出报表          │   │
│  └────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

设计要点：

1. **左侧树形目录**：用 `crm-tree` 组件实现，支持无限层级。分组不是数据库硬约束——只是 UI 层的组织方式，方便管理员归类
2. **右侧表格**：用 `crm-table` 组件展示 Agent 列表，支持搜索、分页
3. **弹窗编辑**：用 `crm-modal` 包裹表单，创建和编辑复用同一个弹窗组件
4. **工具权限控制**：每个 Agent 可以选择性开启 MCP 工具——售前 Agent 不需要「删除客户」权限

#### 为什么需要

- **多智能体协作**：不同部门有不同的 AI 助手（售前、售后、数据分析），共享同一套 CRM 数据但行为不同
- **权限隔离**：通过工具选择控制每个 Agent 的能力边界——防止 AI 越权操作
- **集中管理**：一个界面管理所有智能体的配置、状态、分组

---

## 第三部分：组件体系对比

### 1. crm-table（通用表格组件）

#### 是什么

`crm-table` 是 CordysCRM 的通用表格组件。它把表格的常见逻辑——loading 状态、分页、排序、列配置、数据请求、行选择——封装成一个可复用的组合。

核心是 **useTable composable**（Vue 3 的组合式 API 函数），理念类似 React 的自定义 Hook：把状态和逻辑抽出来，和 UI 解耦。

#### useTable 的设计模式

```typescript
// useTable.ts 核心设计（简化版）
export function useTable(options: UseTableOptions) {
  const loading = ref(false)
  const data = ref([])
  const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
  const sorter = ref(null)

  // 数据加载函数——由调用方传入具体的 API 请求
  async function loadData() {
    loading.value = true
    try {
      const params = {
        page: pagination.page,
        pageSize: pagination.pageSize,
        ...sorter.value,       // 排序参数
        ...options.extraParams // 额外筛选条件
      }
      const res = await options.fetchApi(params)
      data.value = options.transformData  // 👈 数据转换回调
        ? options.transformData(res.data)
        : res.data
      pagination.total = res.total
    } finally {
      loading.value = false
    }
  }

  // 分页变化 → 重新加载
  function onPageChange(page) {
    pagination.page = page
    loadData()
  }

  return { loading, data, pagination, onPageChange, loadData, sorter }
}
```

使用方式：

```vue
<script setup>
import { useTable } from '@crm/shared'
import { getCustomerList } from '@/api/customer'

const { loading, data, pagination, onPageChange } = useTable({
  fetchApi: getCustomerList,              // 👈 传入 API 函数
  extraParams: { status: 'active' },      // 额外筛选
  transformData: (raw) => raw.map(item => ({  // 数据转换
    ...item,
    createdAt: formatDate(item.createdAt)
  }))
})
</script>

<template>
  <crm-table
    :loading="loading"
    :data="data"
    :pagination="pagination"
    @page-change="onPageChange"
  />
</template>
```

#### 和直接手写 table 的区别

**手写方式**（不用封装）：

```vue
<!-- 每个页面都要写一遍这些逻辑 -->
<script setup>
const loading = ref(false)
const data = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

async function fetchData() {
  loading.value = true
  const res = await api.getCustomers({ page: page.value, pageSize: pageSize.value })
  data.value = res.data
  total.value = res.total
  loading.value = false
}
// ... 重复 20 行
</script>
```

**封装后**：每个表格页面只需 5 行代码。loading、分页、错误处理、数据转换——全部由 `useTable` 统一处理。

#### 为什么需要

- **DRY 原则**（Don't Repeat Yourself）：30+ 个页面有表格，不能把同样的分页逻辑写 30 遍
- **一致性**：所有表格的 loading 动画、分页样式、空数据提示——完全一致
- **可测试**：`useTable` 是一个纯函数，可以单独写单元测试

---

### 2. crm-card（卡片容器组件）

#### 是什么

`crm-card` 是一个内容容器组件，提供三段式插槽结构：**header**（标题区）、**content**（内容区）、**footer**（底部操作区）。

```vue
<crm-card title="客户信息" :loading="isLoading">
  <template #header>
    <!-- 标题右侧的额外操作，如「导出」按钮 -->
    <n-button @click="exportData">导出</n-button>
  </template>

  <template #default>
    <!-- 主体内容 -->
    <p>这里放任何内容</p>
  </template>

  <template #footer>
    <!-- 底部操作按钮 -->
    <n-button type="primary" @click="save">保存</n-button>
  </template>
</crm-card>
```

渲染效果：

```
┌────────────────────────────────────┐
│  客户信息              [导出按钮]   │  ← header 插槽
├────────────────────────────────────┤
│                                    │
│  主体内容（任意组件/HTML）           │  ← default 插槽
│                                    │
├────────────────────────────────────┤
│              [保存]                │  ← footer 插槽
└────────────────────────────────────┘
```

关键特性：
- `loading` 属性：为 true 时整个卡片显示骨架屏，内容区域不可见
- `autoHeight`：自动撑满父容器高度
- `noContentPadding`：去掉内容区的默认内边距（表格等需要撑满的场景）

#### 为什么需要

管理后台 90% 的页面内容都是「卡片包裹」的形式。没有 `crm-card`，每个开发者会写出不同样式的卡片——圆角不一样、间距不一样、loading 态处理不一样。统一的卡片组件保证了**视觉一致性**。

---

### 3. crm-modal（弹窗组件）

#### 是什么

`crm-modal` 是弹窗组件，支持两种常见模式：

**表单弹窗**（Form Modal）：

```vue
<crm-modal
  v-model:visible="showModal"
  title="新建客户"
  :loading="submitting"
  @confirm="handleSubmit"
>
  <crm-form-create :schema="customerSchema" v-model="formData" />
</crm-modal>
```

- `v-model:visible` 控制显示/隐藏
- `@confirm` 点击确定按钮时触发
- `:loading` 提交中时确定按钮显示 loading 动画，防止重复提交
- 内容区放表单组件

**确认弹窗**（Confirm Modal）：

```vue
<crm-modal
  type="confirm"
  title="确认删除"
  content="确定要删除客户「张三」吗？此操作不可撤销。"
  :loading="deleting"
  @confirm="handleDelete"
/>
```

#### 为什么需要

和 `crm-table` 同理——统一性。如果每个页面自己用 Naive-UI 的 `n-modal` 写，footer 按钮的排列、loading 态的处理、遮罩层的层级都会不一致。`crm-modal` 把这些细节封装掉。

---

### 4. 纯组件（pure/）vs 业务组件（business/）

#### 是什么

CordysCRM 的前端组件分两个目录：

```
components/
├── pure/           # 纯组件（30+）—— 通用、无业务逻辑
│   ├── crm-table
│   ├── crm-card
│   ├── crm-modal
│   ├── crm-split-panel
│   ├── crm-tree
│   ├── crm-tag
│   ├── crm-upload
│   ├── crm-advance-filter
│   ├── crm-pagination
│   ├── crm-search-input
│   └── ...
│
└── business/       # 业务组件 —— 包含业务逻辑
    ├── CustomerCard        # 客户信息卡片（知道客户数据长什么样）
    ├── ContractTimeline    # 合同时间线
    ├── SalesFunnel         # 销售漏斗图
    └── ...
```

**纯组件特征**：
- 没有具体的业务知识——不知道「客户」是什么
- 通过 props 接收数据，通过 emit 向外通知
- 可以跨项目复用（甚至开源出去）
- 例子：`crm-table` 不知道里面展示的是客户还是合同

**业务组件特征**：
- 绑定具体的数据模型（`Customer`、`Contract`）
- 包含业务规则（如「合同金额 > 100 万标红」）
- 调用具体的 API
- 例子：`CustomerDetailCard` 知道客户有哪些字段、如何格式化

#### 为什么需要分层

```
pure/     ← 像乐高基础砖块，不关心你搭什么
business/ ← 像乐高套装里的特殊件，知道自己在搭城堡还是飞船
```

分层的价值：
1. **复用性**：`crm-table` 在 30+ 个页面里用，只写一遍
2. **可维护性**：改表格样式只动 `crm-table`，不影响任何业务页面
3. **可测试性**：纯组件没有副作用，测试起来很简单

---

## 第四部分：低代码表单 vs 对话式表单

### 1. CordysCRM 的低代码表单

#### 是什么

CordysCRM 的智能实体/低代码表单机制，核心思路是：**用 JSON schema 描述表单结构，组件自动渲染**——不需要手写每个字段的 `<n-input>`。

三个核心组件：

| 组件 | 作用 |
|---|---|
| `crm-form-design` | **表单设计器**——拖拽式可视化设计，生成 schema JSON |
| `crm-form-create` | **表单渲染器**——读取 schema，自动生成带校验的表单 |
| `crm-form-create-drawer` | **抽屉式表单**——从侧边滑出的表单面板（常用于「快速新建」场景）|

#### 工作流程

```
1. 管理员在「表单设计器」里拖拖拽拽
   ↓
2. 生成一个 JSON schema，存入数据库
   ↓
3. 用户打开页面时，crm-form-create 读取 schema
   ↓
4. 自动渲染出完整的表单（字段、校验规则、布局、联动）
```

Schema 示例：

```json
{
  "fields": [
    {
      "type": "input",
      "label": "客户名称",
      "name": "customerName",
      "required": true,
      "placeholder": "请输入客户名称"
    },
    {
      "type": "select",
      "label": "客户等级",
      "name": "level",
      "options": [
        { "label": "VIP", "value": "vip" },
        { "label": "普通", "value": "normal" }
      ]
    },
    {
      "type": "date",
      "label": "下次联系日期",
      "name": "nextContactDate"
    }
  ]
}
```

`crm-form-create` 读到这个 schema，自动渲染出：
- 一个必填的文本输入框「客户名称」
- 一个下拉选择框「客户等级」
- 一个日期选择器「下次联系日期」

**低代码表单的本质**：把「写 Vue 模板代码」变成「写 JSON 配置」。业务人员甚至不需要懂代码，在可视化设计器里拖拽就能搭出表单。

---

### 2. CRMBOT 的对话式参数提取

#### 是什么

CRMBOT 不走传统表单路线——它用 **AI 对话** 来收集参数。用户在聊天框里自然语言描述需求，AI 自动提取关键信息，然后生成对应的文档（报价单、合同、预约单等）。

#### 工作流程（基于 LangGraph 状态图）

```
用户输入：「我要给深圳科技公司报个价，产品是 CRM 系统企业版，数量 50 个账号」

   ┌──────────────┐
   │  intent_node │  识别意图 → "quotation"（报价）
   └──────┬───────┘
          ↓
   ┌──────────────┐
   │ response_node│  追问缺失信息：
   │              │  「请问客户的联系人和电话是？」
   └──────┬───────┘
          ↓
   ┌──────────────┐
   │ response_node│  用户补充 → 参数收集完毕
   │  (第二轮)     │
   └──────┬───────┘
          ↓
   ┌──────────────┐
   │document_nodes│  生成报价单文档（填充模板）
   │  (quotation) │  → 返回 Word/PDF 下载链接
   └──────────────┘
```

关键节点：

**intent_node（意图识别）**——识别 7 种意图：

```python
# intent_node.py 核心逻辑（简化）
INTENTS = {
    "greeting":         "问候寒暄",
    "product_inquiry":  "产品咨询",
    "quotation":        "报价请求",
    "contract":         "合同生成",
    "appointment":      "预约安排",
    "complaint":        "投诉处理",
    "negotiation":      "价格谈判",
    "general":          "通用问答",
}
```

**response_node（对话追问）**——根据意图类型，用对话方式收集缺失参数。比如报价需要：客户名称、产品、数量、单价。如果用户第一次没说全，AI 用自然语言追问。

**document_nodes（文档生成）**——参数齐全后，调用对应模板生成文档。目前支持 4 种合同模板 + 报价单。

---

### 3. 两种路线的优劣对比

| 维度 | 低代码表单（CordysCRM） | AI 对话式表单（CRMBOT） |
|---|---|---|
| **开发效率** | ⭐⭐⭐⭐⭐ Schema 驱动，改配置就行 | ⭐⭐⭐ 需要设计 prompt、处理边界 |
| **用户体验** | ⭐⭐⭐ 点来点去填字段 | ⭐⭐⭐⭐⭐ 自然语言，说人话就行 |
| **一致性** | ⭐⭐⭐⭐⭐ 所有表单统一渲染 | ⭐⭐ 对话不保证参数完整 |
| **灵活性** | ⭐⭐ 超出 schema 定义的行为很难做 | ⭐⭐⭐⭐ 用户可以自由描述 |
| **可控性** | ⭐⭐⭐⭐⭐ 字段必填、格式校验、一步不落 | ⭐⭐ AI 可能遗漏参数或理解偏差 |
| **适用场景** | 后台管理、标准化数据录入 | 面向终端用户、非标需求、自然交互 |

#### CRMBOT 的正确路线

> **AI 对话是主交互 + 后台管理用低代码表单提升效率**

这个组合是最务实的：

```
外部客户侧（CRMBOT 聊天界面）：
  用户 → 自然语言对话 → AI 提取参数 → 生成文档
  优势：零学习成本，用户不需要知道「合同模板」是什么

内部管理侧（CRMBOT 后台）：
  管理员 → 低代码表单 → 配置产品库/合同模板/价格表
  优势：标准化的配置管理，不会因为 AI 幻觉导致数据错误
```

具体来说：
- **聊天界面**保持对话式交互（CRMBOT 当前已有）
- **后台管理**（文档列表、模板管理、产品库）用低代码表单，参考 CordysCRM 的 `crm-form-create` 模式——用 schema 定义字段，自动渲染表格 + 表单 + 搜索，节省大量 CRUD 代码
- **集成 MCP**：未来让 CRMBOT 通过 MCP 连接 CordysCRM，把「查询客户」「创建合同」等操作也融入对话流程

---

## 第五部分：技术术语小词典

| 术语 | 一句话解释 |
|---|---|
| **SPA** | 单页应用——浏览器只加载一次 HTML，后续页面切换由 JS 在本地完成，不刷新 |
| **SSR** | 服务端渲染——HTML 在服务器上生成好后发给浏览器，首屏快、SEO 友好 |
| **CSR** | 客户端渲染——HTML 在浏览器里用 JS 动态生成（SPA 就是 CSR 的一种） |
| **Virtual DOM** | 虚拟 DOM——内存里的一个轻量 DOM 树副本，框架用它算出差量后只更新真实 DOM 中变化的部分 |
| **Composable / Hook** | Vue 叫 Composable、React 叫 Hook——把组件逻辑抽成可复用函数的机制 |
| **Store / 状态管理** | 全局数据仓库——多个组件共享的状态（如用户信息、购物车）不放组件内部，放在 store 里集中管理 |
| **RESTful API** | 一种 API 设计风格——用 URL 表示资源（`/users/42`），用 HTTP 方法表示操作（GET 查、POST 增、PUT 改、DELETE 删） |
| **WebSocket** | 全双工通信协议——客户端和服务器可以随时互发消息，不像 HTTP 只能客户端先请求 |
| **Docker / 容器化** | 把应用和它的依赖打包成一个「集装箱」，在任意机器上一键运行，环境完全一致 |
| **ORM** | 对象关系映射——用面向对象的方式操作数据库，写 `User.objects.filter(name="张三")` 而不是写 SQL |
| **MCP** | Model Context Protocol——Anthropic 提出的开放协议，让 AI 模型以统一方式调用外部工具 |
| **RAG** | 检索增强生成——AI 回答前先去知识库检索相关文档，把文档内容「喂」给模型，减少幻觉 |
| **LangGraph** | LangChain 的状态图框架——用有向图（节点 + 边）编排 AI 工作流，适合多步骤 Agent |

---

## 附录：两个项目的快速对比

| | CordysCRM | CRMBOT |
|---|---|---|
| **定位** | 传统 CRM 系统 + AI 能力外挂 | AI 原生对话式 CRM 助手 |
| **后端** | Java / Spring Boot / MyBatis | Python / FastAPI / LangGraph |
| **前端** | Vue 3 / Vite / Naive-UI / Monorepo | React 19 / Vite / Tailwind / 单应用 |
| **表单方式** | 低代码 schema 驱动 | AI 对话式参数提取 |
| **AI 集成** | MCP Server（暴露工具给外部 AI） | 内置 DeepSeek V4（对话 + 文档生成） |
| **路由** | Vue Router（嵌套路由、布局系统） | 暂无（只有单聊天界面） |
| **组件体系** | pure/ 纯组件 + business/ 业务组件 | shadcn/ui 原子组件 |
| **当前阶段** | 成熟产品 | 阶段零完成（7 模块 / 17 路由 / Docker 化） |

---

*文档完成于 2026 年 6 月。两个项目都在快速迭代中，本文档反映的是当前阶段的技术架构。*
