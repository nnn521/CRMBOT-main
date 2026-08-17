# Bug 复盘：B端人工消息 → C端 WS 实时推送不显示

> **时间**: 2026-06-19 19:13 ~ 20:03  
> **分支**: `dev`  
> **影响**: C端（客户聊天页）收不到 B端（管理后台）人工模式发送的消息

---

## 一、现象

B端选中会话 `session_admin`，切换人工模式，发送消息。B端自己能看见消息，但 C端页面通过 WebSocket 收不到实时推送，聊天气泡不更新。

---

## 二、排查过程

### 阶段 1：加 Debug Bar 观察数据流

在 C端 (`App.tsx`) 页面顶部加一个 WS Debug Bar，显示：
- WebSocket 连接状态
- 收到的消息总数 (`msgs=N`)
- 最后一条消息内容 (`last={...}`)  
- 消息匹配诊断 (`hint`)

在 B端 (`ChatContent.tsx`) 聊天区顶部加 Debug Bar，显示：
- 当前选中的会话 ID
- 当前模式（AI / human）
- API 发送状态（成功 / 失败原因）

**发现**：C端 WS 已连接，`msgs` 在增长（收到 pong 心跳），但 `last` 始终是 `{"type":"pong"}`，没有 `new_message` 类型。说明 B端的消息没触发 WebSocket 广播。

### 阶段 2：B端发送逻辑问题

B端 Debug Bar 显示 `mode=human`，但发消息后没有显示 `✅ Sent OK`。

**原因**：Vite 开发服务器缓存了旧代码。`curl http://localhost:5173/src/components/ChatContent.tsx` 返回的内容不包含新增的 `bsendStatus`。

**解决**：
```bash
fuser -k 5173/tcp          # 杀死旧进程
rm -rf node_modules/.vite  # 清 Vite 缓存
npx vite --force            # 强制重新构建
```

### 阶段 3：后端不稳定

后端使用 shell 的 `&` 后台运行，经常自己挂掉，导致 B端 API 调用失败。

**解决**：使用 tmux 托管两个服务进程：
```bash
tmux new-session -d -s cbt-backend "cd backend && uvicorn app.main:app ..."
tmux new-session -d -s cbt-frontend "cd frontend && npx vite ..."
```
tmux 创建的 session 独立于 shell，父进程退出也不会被 kill。

### 阶段 4：消息到了浏览器但气泡不更新

Debug Bar 显示：
```
msgs=4  ✅ MATCH  last={"type":"new_message","session_id":"session_admin","message":{"reply":"222"...}}
```

- ✅ WS 已连接
- ✅ 收到了 `new_message` 类型
- ✅ `session_id` 匹配（`session_admin`）
- ✅ 消息内容包含 `reply: "222"`
- ❌ 但聊天气泡里没有显示 "222"！

在 `trackedHandler` 中加了 try/catch 捕获异常 → 发现 `handleWsMessage` 没有抛出异常。但消息数量没增加：`✅ MATCH → msgs[2]`（一直是 2 条，没有变 3 条）。

### 阶段 5：根因定位 🔥

进一步加诊断后，发现 `handleWsMessage` 内部调用 `addMessage()` 报错。追查调用链：

```
App.tsx
  const { addMessage } = useChat()           ← 这里！
           ↓
useChat.ts
  const { addMessage } = useChatStore()      ← addMessage 从 store 取到了
  return { messages, isLoading, sessionId,
           attachedDocs, attachedImages,
           sendMessage }                      ← 但没有导出 addMessage！
```

**根因**：`useChat()` hook 从 Zustand store 解构了 `addMessage`，但在 `return` 语句中**忘了把它暴露出去**。App.tsx 中 `const { addMessage } = useChat()` 拿到的是 `undefined`。当 WebSocket 收到人工消息后调用 `addMessage(...)` → `TypeError: addMessage is not a function` → 被 WS `onmessage` 的 try/catch 捕获并静默吞掉 → 消息丢失，用户无感知。

**修复**（`useChat.ts`，1 行）：
```diff
  return {
    messages,
    isLoading,
    sessionId,
    attachedDocs,
    attachedImages,
    sendMessage,
+   addMessage,
  }
```

### 阶段 6：附带问题 — B端消息显示位置错误

B端人工模式发送的消息出现在**左侧**（AI 气泡位置），应该在右侧（用户气泡位置）。

**原因**：本地添加消息时用了 `role: 'assistant'`，ChatBubble 组件根据 `role === 'user'` 决定左右对齐。

**修复**：将 `role: 'assistant'` → `role: 'user'`。

---

## 三、完整数据流（正常后）

```
B端 management page                    C端 customer chat
─────────────────────                  ─────────────────────
handleAdminSend("222")
  ↓
setLocalMessages(role:'user')  →  B端自己看到 "222"（右侧）
  ↓
sendHumanMessage(sessionId, "222")
  ↓
POST /api/v1/chat/sessions/
  session_admin/human-message         WebSocket ws://.../ws/session_admin
  ↓                                     ↑
backend: save + broadcast               │ 收到 {"type":"new_message","message":{"reply":"222"}}
                                        │   ↓
                                        │ handleWsMessage(data)
                                        │   data.session_id === 'session_admin' ✅
                                        │   reply = "222" ✅
                                        │   addMessage({role:'assistant', content:'222'})
                                        │     ↓
                                        │   useChatStore.messages.push(...)
                                        │     ↓
                                        │   React re-render → 气泡显示 "222" ✅
```

---

## 四、关键教训

| # | 问题 | 教训 |
|---|------|------|
| 1 | `useChat()` 忘了导出 `addMessage` | 自定义 hook 的 return 值要仔细和调用方对齐；TypeScript 没报错是因为 `useChat` 没有显式返回类型注解，推断类型中不包含未导出的属性，但解构赋值时 TS 允许取不存在的 key |
| 2 | Vite 缓存不更新 | `rm -rf node_modules/.vite` + 重启 vite 加 `--force`；开发调试时要注意 HMR 可能没生效 |
| 3 | 后台进程挂掉 | 不要用 `&` 跑服务进程，用 `tmux new-session -d` 托管 |
| 4 | 错误被静默吞掉 | WS `onmessage` 的 try/catch 会吞掉异常，导致消息丢失但用户无感知。处理异步回调时应该在关键路径上加可见的错误提示 |
| 5 | Debug Bar 策略 | 从外到内逐层加 Debug：WS 层 → handler 层 → store 层，每一层确认数据是否到位 |

---

## 五、相关文件

- `frontend/src/hooks/useChat.ts` — **修复点**：return 增加 `addMessage`
- `frontend/src/App.tsx` — C端，WS 消息处理
- `frontend/src/components/ChatContent.tsx` — B端，人工消息发送
- `frontend/src/api/chat.ts` — `sendHumanMessage()` API 封装
- `frontend/src/hooks/useWebSocket.ts` — WebSocket hook，onmessage 中的 try/catch 吞异常
- `backend/app/api/v1/chat.py` — 人工消息 API endpoint + WebSocket broadcast
