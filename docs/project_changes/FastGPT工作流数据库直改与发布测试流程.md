# FastGPT工作流数据库直改与发布测试流程

## 1. 目标

本文记录在当前服务器环境下，如何通过直接修改 FastGPT 数据库来：

- 自动化修改工作流
- 自动化发布工作流
- 自动化测试工作流
- 自动化回滚工作流

该流程适用于当前部署环境中的 FastGPT 单实例。

## 2. 当前环境

### 2.1 相关容器

- `fastgpt`
- `fastgpt-mongo`
- `fastgpt-redis`
- `fastgpt-pg`

### 2.2 当前线上应用

当前数据库中实际只有一个应用：

- 应用名：`服务器测试`
- `appId`：`69e5ebb5614a51c203e67b9a`

### 2.3 Mongo 连接信息

来自部署配置：

```text
mongodb://myusername:mypassword@fastgpt-mongo:27017/fastgpt?authSource=admin
```

在容器外通过 Docker 执行：

```bash
sudo docker exec fastgpt-mongo mongo -u myusername -p mypassword --authenticationDatabase admin fastgpt --quiet --eval '...'
```

## 3. 数据结构说明

### 3.1 草稿

工作流编辑中的当前草稿保存在：

- `fastgpt.apps`

关键字段：

- `modules`
- `edges`
- `chatConfig`
- `updateTime`

### 3.2 已发布版本

工作流“保存并发布”后的版本保存在：

- `fastgpt.app_versions`

关键字段：

- `appId`
- `nodes`
- `edges`
- `chatConfig`
- `versionName`
- `isPublish`
- `time`
- `tmbId`

### 3.3 运行时行为

实际测试已确认：

- OpenAPI 调用使用的是 `app_versions`
- 只修改 `apps.modules` 不会影响对外 API
- 要让 API 生效，必须新增一条发布版本记录，等价于 UI 中“保存并发布”

## 4. 查询当前工作流

### 4.1 查询唯一应用

```bash
sudo docker exec fastgpt-mongo mongo -u myusername -p mypassword --authenticationDatabase admin fastgpt --quiet --eval '
print("apps count", db.apps.count());
db.apps.find({}, {_id:1,name:1,type:1,updateTime:1,version:1}).forEach(function(doc){printjson(doc)});
'
```

### 4.2 查询发布版本

```bash
sudo docker exec fastgpt-mongo mongo -u myusername -p mypassword --authenticationDatabase admin fastgpt --quiet --eval '
var appId=ObjectId("69e5ebb5614a51c203e67b9a");
db.app_versions.find({appId:appId}).sort({time:-1}).forEach(function(v){printjson(v)});
'
```

## 5. 修改工作流草稿

### 5.1 原则

- 只修改目标节点，不改无关模块
- **修改提示词前必须先检查所有 `{{$...$}}` 变量引用，确保修改后的文本中引用完整保留**
- 优先改 `modules[*].inputs[*].value`
- 修改后同步更新 `apps.updateTime`
- 修改前必须备份

### 5.2 备份草稿

```bash
sudo docker exec fastgpt-mongo mongo -u myusername -p mypassword --authenticationDatabase admin fastgpt --quiet --eval '
var app=db.apps.findOne({_id:ObjectId("69e5ebb5614a51c203e67b9a")});
print(JSON.stringify(app));
'
```

建议保存到：

- `fastGPT_json/backups/`

### 5.3 修改示例

典型场景是改 contentExtract 节点的提示词（`description` 字段）：

**步骤：**

1. 读取 `apps` 中目标应用
2. 遍历 `modules`，按 `name` 找到目标节点
3. **先检查该节点所有 inputs 中包含哪些 `{{$...$}}` 变量引用**（常见于 `description`、`content` 字段）：
   ```bash
   sudo docker exec fastgpt-mongo mongo ... --eval '
   v.nodes.forEach(function(n) {
     if (n.name && n.name.indexOf("目标节点名") !== -1) {
       n.inputs.forEach(function(inp) {
         if (typeof inp.value === "string" && inp.value.indexOf("{{$") !== -1) {
           print(inp.key + ": " + inp.value);
         }
       });
     }
   });
   '
   ```
4. 修改提示词文本时**确保所有 `{{$nodeId.key$}}` 引用完整保留**，不能删除、截断或误改
5. 执行修改前全文 diff 确认只有预期内容变化
6. `db.apps.updateOne(...)` 更新草稿
7. 发布新版 `app_versions` 并校验 edges 非空

**改 HTTP 节点请求体同理：**

- `system_httpJsonBody`
- `system_httpReqUrl`
- `system_httpMethod`

示例逻辑：

1. 读取 `apps` 中目标应用
2. 遍历 `modules`
3. 按 `nodeId` 或 `name` 找到要改的节点
4. 修改目标 `inputs` 的 `value`
5. `db.apps.updateOne(...)`

## 6. 自动发布

### 6.1 核心原则

自动发布不是只改 `apps`，而是要新增一条 `app_versions`。

### 6.2 发布流程

1. 读取当前 `apps` 草稿
2. 取出：
   - `modules`
   - `edges` （**必须显式取出，不可省略**）
   - `chatConfig`
   - `tmbId`
   - `teamId`
3. 写入 `app_versions`
4. 设置：
   - `appId`
   - `nodes = app.modules`
   - `edges = app.edges` （**必须显式赋值，不能依赖隐式继承**）
   - `chatConfig = app.chatConfig`
   - `teamId = app.teamId`
   - `isPublish = true`
   - `versionName = 当前时间`
   - `time = 当前时间`
5. **发布后立即校验** `edges` 是否存在且长度 > 0

### 6.3 关键坑

**坑1：edges 丢失导致工作流链路断开**

发布时如果 `edges` 字段遗漏为 `undefined` 或空数组，工作流中节点之间没有连接关系，FastGPT 只会执行到入口节点 `pluginInput` 就停止，下游的 `chatNode`、`pluginOutput` 等全部不执行。

**症状**：API 返回 `responseData` 只有一条 `workflow:template.plugin_start / pluginInput`，`choices[0].message.content` 为空。

**原因**：构建新 `app_versions` 记录时忘记显式设置 `edges` 字段，或从旧版本读取时未正确取出。

**修复**：从旧版本复制 `edges` 数组覆盖新版本即可，不需要重建 `nodes`。

```bash
sudo docker exec fastgpt-mongo mongo -u myusername -p mypassword \
  --authenticationDatabase admin fastgpt --quiet --eval '
var oldV = db.app_versions.findOne({_id: ObjectId("<旧版本_id>")});
var newV = db.app_versions.findOne({_id: ObjectId("<新版本_id>")});
if (!newV.edges || newV.edges.length === 0) {
  db.app_versions.updateOne(
    {_id: ObjectId("<新版本_id>")},
    {$set: {edges: oldV.edges}}
  );
}
'
```

**预防**：发布脚本中构建 `newVersion` 对象时，务必显式包含 `edges` 字段并发布后校验：

```javascript
var newVersion = {
  ...
  edges: latestVersion.edges,  // 必须显式赋值，不能省略
  ...
};
var result = db.app_versions.insertOne(newVersion);
// 立即校验
var verify = db.app_versions.findOne({_id: result.insertedId});
if (!verify.edges || verify.edges.length === 0) {
  print("ERROR: edges missing!");
}
```

---

**坑2：tmbId 类型错误**

`app_versions.tmbId` 不能写成：

```text
ObjectId("69e5d756215f9968f4fab5de")
```

这种字符串。

否则 FastGPT UI 打开团队云端版本时会报：

```text
Cast to ObjectId failed for value "ObjectId(...)"
```

正确写法应为普通 24 位字符串：

```text
69e5d756215f9968f4fab5de
```

另外，`app_versions.tmbId` 也不能写成：

```text
[object Object]
```

这通常发生在脚本里把 Mongo 返回的 `ObjectId` 对象直接做字符串拼接或模板渲染，最终被 JavaScript 隐式转成了 `"[object Object]"`。

否则 FastGPT UI 打开团队云端版本时会报：

```text
Cast to ObjectId failed for value "[object Object]" (type string) at path "_id" for model "team_members"
```

### 6.4 发布字段类型注意事项

发布时必须遵守以下字段约束：

- `app_versions.tmbId`
  - 正确：24 位字符串，例如 `69e5d756215f9968f4fab5de`
  - 错误：`ObjectId("...")`
  - 错误：`[object Object]`

- `app_versions.teamId`
  - 应显式写入
  - 推荐直接写 Mongo `ObjectId`
  - 不要省略

- `app_versions.appId`
  - 必须是 Mongo `ObjectId`

### 6.5 从草稿读取并发布时的安全做法

如果是脚本自动发布，推荐：

1. 先从 `apps` 读取原始文档
2. 对 `tmbId` 做显式转换
   - 若要写字符串，则写 `String(app.tmbId).replace(/^ObjectId\\(\"(.*)\"\\)$/,'$1')`
   - 更稳妥的方式是在发布脚本里直接写固定的 24 位字符串值
3. 对 `teamId` 明确写入 `ObjectId("...")`
4. 不要把整个 `app` 对象直接 `JSON.stringify` 后再指望 Mongo 自动恢复字段类型
5. 发布后立即查询 `app_versions` 做校验

校验命令示例：

```bash
sudo docker exec fastgpt-mongo mongo -u myusername -p mypassword --authenticationDatabase admin fastgpt --quiet --eval '
var appId=ObjectId("69e5ebb5614a51c203e67b9a");
db.app_versions.find({appId:appId}).sort({time:-1}).limit(5).forEach(function(v){
  printjson({_id:v._id, versionName:v.versionName, tmbId:v.tmbId, teamId:v.teamId, time:v.time});
});
'
```

## 7. 自动测试

### 7.1 API Key 存档

当前本机已使用隐藏目录保存应用特定 key：

- `/home/ubuntu/.fastgpt_keys/app_api_key`

权限建议：

```bash
chmod 600 /home/ubuntu/.fastgpt_keys/app_api_key
```

### 7.2 对话接口

Base URL：

```text
http://127.0.0.1:3000/api
```

调用接口：

```text
POST /api/v1/chat/completions
```

Header：

```text
Authorization: Bearer <app-api-key>
Content-Type: application/json
```

### 7.3 测试示例

```bash
curl --location --request POST 'http://127.0.0.1:3000/api/v1/chat/completions' \
--header 'Authorization: Bearer fastgpt-xxxxxx' \
--header 'Content-Type: application/json' \
--data-raw '{
  "chatId": "codex-test-001",
  "stream": false,
  "detail": true,
  "messages": [
    {
      "role": "user",
      "content": "电力电缆绝缘劣化与击穿故障的原因、现象和应对措施是什么？"
    }
  ],
  "customUid": "codex-test"
}'
```

### 7.4 detail=true 的用途

设置 `detail=true` 后，可以返回完整工作流运行链路，包括：

- 哪个模块被执行
- HTTP 节点请求体
- HTTP 返回内容
- 提取结果
- 代码节点输出
- 模型生成过程

这对于验证“数据库直改后工作流是否真的走到新版本”非常关键。

## 8. 回滚流程

### 8.1 回滚原则

回滚不一定要删版本。

更稳的方式是：

1. 找到目标旧版本的 `app_versions`
2. 用旧版本的：
   - `nodes`
   - `edges`
   - `chatConfig`
3. 覆盖 `apps`
4. 再重新插入一条新的 `app_versions`

这样回滚后又形成一个新的已发布版本，和 UI 操作习惯一致。

### 8.2 必须先备份

建议至少备份：

- 当前 `apps` JSON
- 当前全部 `app_versions` JSONL

当前目录建议：

- `fastGPT_json/backups/`

## 9. 本次实际结论

### 9.1 已确认的事实

- 当前环境中只有一个应用：`服务器测试`
- `apps` 是草稿
- `app_versions` 是发布版本
- OpenAPI 测试走的是 `app_versions`

### 9.2 已踩过的坑

1. 只改 `apps.modules`，API 不生效
2. **发布 `app_versions` 时 `edges` 字段遗漏为 `undefined`**，导致工作流节点断开，API 只执行入口节点就停止（2026-04-26，并行生成插件 & 基本信息获取插件各一次）
3. **修改 contentExtract 节点 `description` 时未检查 `{{$...$}}` 变量引用**，改完后引用断裂导致上游数据无法传入（2026-04-26，设备识别节点）
4. 手工发布时 `tmbId` 写错成 `ObjectId("...")` 字符串，会导致团队云端版本页面报错
5. FastGPT HTTP 节点里带变量的 nGQL，如果用双引号包变量，运行时可能变成 `\"变量值\"`，进而导致 Nebula 语法错误

### 9.3 已验证有效的方式

- 修改草稿
- 新增 `app_versions`
- 用 OpenAPI + `detail=true` 做端到端验证

## 10. 推荐操作顺序

1. 备份 `apps` 和 `app_versions`
2. 修改 `apps.modules`
3. 新增 `app_versions` 实现发布（**显式保证 `edges`、`tmbId`、`teamId` 字段完整**）
4. 发布后立即校验新版本的 `edges` 非空、`tmbId` 格式正确
5. 用 API 跑 `detail=true` 测试
6. 如果失败，修正后再次发布
7. 如果需要回滚，从旧版本恢复并重新发布

## 11. 风险提示

- 不要直接批量改多个应用；当前虽然只有一个应用，但后续多应用时必须按 `appId` 精确过滤
- 不要把 `ObjectId("...")` 作为普通字符串写入外键字段
- 不要把 Mongo 的 `ObjectId` 对象直接拼接成字符串，否则很容易写出 `"[object Object]"`
- 发布版本记录里不要漏写 `teamId`
- 不要只改草稿后就认为上线成功
- 不要在未备份的情况下直接删 `app_versions`
