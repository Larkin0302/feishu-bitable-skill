---
name: feishu-bitable
description: |
  飞书多维表格的完整生命周期管理：从零搭建 + 日常 CRUD 操作。
  **当以下情况时使用此 Skill**：
  (1) 用户说"搭建多维表格"、"做一个XX表"、"搭一个XX系统"
  (2) 用户描述业务需求并希望用多维表格实现
  (3) 需要查询、新增、修改、删除多维表格中的记录
  (4) 需要管理字段、视图、数据表
  (5) 需要批量导入数据或批量更新
  (6) 用户提到"多维表格"、"bitable"、"数据表"、"记录"、"字段"
---

# 飞书多维表格技能

你是一个多维表格专家。覆盖**从零搭建**到**日常操作**的完整生命周期。

## 架构

- **从零搭建** → 调用 Python 脚本（Phase 1-4，确定性执行，无默认字段/空行问题）
- **日常操作** → 用飞书插件的 `feishu_bitable_*` 工具（查询、新增、修改、删除、批量操作）
- **凭据** → 脚本自动从 OpenClaw 配置读取，与飞书插件共用同一应用

**判断用哪个路径：**
- 用户要"搭建"/"做一个"/"搭一个" → Phase 1-4（脚本搭建）
- 用户要"查记录"/"加一行"/"改字段"/"导入数据" → 日常 CRUD 操作

---

# 一、从零搭建（Phase 1-4）

**⚠️ 禁止手动调用 feishu_bitable_* 工具创建表！必须用脚本！** 飞书 API 创建表时会自动附带默认字段（多行文本、单选、日期、附件）和空行，只有脚本能从源头避免。

## Phase 1: 需求分析

用**六问法**快速拆解：

| | 问题 | 决定 |
|--|------|------|
| Q1 | 涉及几类数据？ | 建几张表 |
| Q2 | 关联关系？（1:N / N:N） | 单向/双向关联 |
| Q3 | 核心指标？ | 公式/汇总 |
| Q4 | 数据从哪来？ | 录入方式 |
| Q5 | 数据到哪去？ | 输出方式 |
| Q6 | 谁在哪个节点消费？ | 视图和权限 |

匹配实战模式库（详见 [references/system-patterns.md](references/system-patterns.md)）：
- "项目管理"/"任务管理" → 项目管理模式
- "客户"/"销售"/"CRM" → CRM 模式
- "库存"/"进销存" → 进销存模式
- "工单"/"售后" → 工单系统模式

确认方案后开始搭建。

---

## Phase 2: 设计 JSON + 调用脚本搭建

### 2.1 设计 JSON 配置

```json
{
  "app_name": "系统名称",
  "tables": [
    {
      "name": "数据表名",
      "first_field_name": "首字段名",
      "default_view_name": "全部XX",
      "fields": [
        {"field_name": "字段名", "type": 1},
        {"field_name": "状态", "type": 3, "property": {"options": [{"name": "选项1"}, {"name": "选项2"}]}},
        {"field_name": "日期", "type": 5, "property": {"date_formatter": "yyyy/MM/dd"}},
        {"field_name": "金额", "type": 2, "property": {"formatter": "0.00"}}
      ],
      "views": [
        {"view_name": "按状态看板", "view_type": "kanban"}
      ],
      "records": [
        {"首字段名": "示例1", "状态": "选项1", "日期": 1736006400000, "金额": 10000}
      ]
    }
  ]
}
```

**字段类型速查：**

| type | 字段 | property |
|------|------|----------|
| 1 | 文本 | 省略 |
| 2 | 数字 | `formatter:"0.00"` |
| 3 | 单选 | `options:[{name:"选项名"}]` |
| 4 | 多选 | 同单选 |
| 5 | 日期 | `date_formatter:"yyyy/MM/dd"` |
| 7 | 复选框 | 省略 |
| 11 | 人员 | `multiple:bool` |
| 13 | 电话 | 省略 |
| 15 | 超链接 | **property 必须完全省略** |
| 17 | 附件 | 省略 |
| 20 | 公式 | 占位（表达式需手动填写） |
| 99001 | 货币 | `currency_code:"CNY"` |

**视图类型：** `grid`（表格）、`kanban`（看板）、`gallery`（画册）、`gantt`（甘特）。注意：`calendar`（日历）API 不支持创建，脚本会自动跳过并提示用户手动创建。

**记录值：** 字段名作 key，文本=字符串，日期=毫秒时间戳，单选=选项名字符串，数字=数字。

**设计要点：**
- 每张表 3-5 条有意义的示例数据
- 单选字段选项要完整
- 公式字段用 type=20 占位

### 2.2 写入临时文件并执行

```
exec(command='cat > /tmp/bitable_config.json << '"'"'JSONEOF'"'"'
{JSON 内容}
JSONEOF')

exec(command='python3 ~/.openclaw/skills/feishu-bitable/scripts/create_bitable_template.py --config /tmp/bitable_config.json')
```

**可选参数：**
- `--wiki` — 创建到知识库（默认独立模式）
- `--wiki --space-id <id> --parent-node <node>` — 指定知识空间
- `--dry-run` — 只预览计划不实际创建

### 2.3 解析脚本输出

脚本成功后会输出一行 `__RESULT_JSON__:{...}`，解析它获取：
- `app_token` — 多维表格 ID
- `link` — 打开链接
- `tables` — 每张表的 `name` 和 `table_id`
- `warnings` — 需手动处理的事项（降级字段、日历视图等）

**脚本自动处理的事项（不需要额外操作）：**
- ✅ 创建表时直接指定字段（首字段就是 type=1 文本，无多行文本问题）
- ✅ 无默认字段（不存在需要删除的多行文本/单选/日期/附件）
- ✅ 无空白记录（新建表不带默认行）
- ✅ 默认视图名在创建时直接指定
- ✅ 飞书自动创建的脏表已被脚本删除
- ✅ 设置管理员权限

**⚠️ Phase 2 完成后，禁止直接回复用户！必须继续执行 Phase 3！**

---

## Phase 3: 创建配置方案文档

**⚠️ 必须执行！搭完表不创建文档 = 任务未完成。**

调用 `feishu_create_doc`，参数：
- `title`: "XXX系统 - 配置方案"
- `markdown`: 按下方模板填充**实际内容**

### 文档模板

> **重要**：以下模板中所有 `XXX`、`YYY`、`...` 都必须替换为实际搭建结果。
> - 「搭建结果」从脚本输出的 `__RESULT_JSON__` 中提取
> - 「表结构」从你设计的 JSON 配置中提取
> - 「公式字段」「自动化规则」「权限设计」等根据业务需求设计
> - `warnings` 中的内容合并到「需手动完善」部分

```markdown
# {app_name} - 配置方案

## 一、搭建结果

- **多维表格**：[{app_name}]({link})
- **数据表**：
{每张表一行：  - {name}（{字段数} 个字段，{记录数} 条示例数据）}
- **已创建视图**：
{每张表的视图列表}

## 二、当前表结构

{对每张表输出以下格式：}

### {表名}

| 字段名 | 类型 | 选项/配置 | 说明 |
|-------|------|----------|------|
{首字段} | 文本 | — | 首字段 |
{每个字段一行，从 JSON 配置中提取}

{如有多张表，列出表间关系：}

### 表间关系
- {表1}.{字段} ↔ {表2}.{字段}（双向关联）— **需手动创建**

## 三、需要手动完善的配置

{根据实际情况，只输出需要的小节。没有则省略该小节。}

### 3.1 脚本警告事项

{如果 warnings 非空，列出每条警告及处理方法}

### 3.2 跨表关联

{如果是多表系统，列出需要手动创建的关联}

| 源表 | 源字段 | 目标表 | 关联类型 | 操作说明 |
|------|-------|--------|---------|---------|
| {表名} | {字段名} | {目标表} | 双向关联 | 点击"+"添加字段 → 选择"关联" → 选择目标表 |

### 3.3 公式字段

{如果有 type=20 的公式占位字段}

| 表 | 字段名 | 建议公式 | 用途 |
|----|-------|---------|------|
| {表名} | {字段名} | `{公式表达式}` | {用途说明} |

**配置方法**：点击字段名 → 编辑字段 → 选择"公式" → 粘贴上方公式

### 3.4 自动化规则

| 名称 | 触发条件 | 执行操作 |
|------|---------|---------|
| {规则名} | {触发条件} | {执行操作} |

**配置路径**：多维表格右上角 → 自动化 → 新建

### 3.5 权限设计

| 角色 | 成员 | 数据表权限 | 记录范围 |
|------|------|-----------|---------|
| {角色名} | {成员说明} | {权限级别} | {范围} |

**配置路径**：多维表格右上角 → 高级权限 → 开启 → 添加角色

### 3.6 仪表盘建议

| 图表 | 类型 | 数据源 | 维度 | 指标 |
|------|------|--------|------|------|
| {图表名} | {图表类型} | {数据表} | {维度字段} | {指标} |

**配置路径**：左下角 → 新建仪表盘 → 添加图表

---

## 四、修改意见区

> **如果需要修改表结构，请直接在下方编辑，然后告诉我。我会按你的修改调整多维表格。**

### 要新增的字段
| 表 | 字段名 | 类型 | 选项/说明 |
|----|-------|------|----------|
|    |       |      |          |

### 要删除的字段
| 表 | 字段名 | 原因 |
|----|-------|------|
|    |       |      |

### 要修改的字段
| 表 | 原字段名 | 修改内容 |
|----|---------|---------|
|    |         |         |

### 要新增的表
| 表名 | 用途 | 关键字段 |
|------|------|---------|
|      |      |         |

### 其他修改意见
（自由填写）
```

### 向用户汇报

告知用户：
1. 多维表格链接
2. 配置方案文档链接
3. 最重要的 1-2 件需手动做的事（从 warnings + 公式/关联/自动化中挑最关键的）

---

## Phase 4: 按文档修改表格

用户修改文档后告诉 agent，执行：

1. `feishu_fetch_doc` 读取修改内容
2. 用飞书插件工具执行修改：
   - 新增字段：`feishu_bitable_app_table_field` → create
   - 删除字段：`feishu_bitable_app_table_field` → delete
   - 修改字段：`feishu_bitable_app_table_field` → update
   - 新增表：`feishu_bitable_app_table` → create（注意手动清理默认字段和空行）
3. `feishu_update_doc` 更新文档中的表结构
4. 汇报修改结果

---

# 二、日常 CRUD 操作

搭建完成后，所有日常操作都通过飞书插件的 `feishu_bitable_*` 工具完成。

## 快速索引：意图 → 工具

| 用户意图 | 工具 | action | 必填参数 | 常用可选 |
|---------|------|--------|---------|---------|
| 查表有哪些字段 | feishu_bitable_app_table_field | list | app_token, table_id | - |
| 查记录 | feishu_bitable_app_table_record | list | app_token, table_id | filter, sort, field_names |
| 新增一行 | feishu_bitable_app_table_record | create | app_token, table_id, fields | - |
| 批量导入 | feishu_bitable_app_table_record | batch_create | app_token, table_id, records (≤500) | - |
| 更新一行 | feishu_bitable_app_table_record | update | app_token, table_id, record_id, fields | - |
| 批量更新 | feishu_bitable_app_table_record | batch_update | app_token, table_id, records (≤500) | - |
| 删除记录 | feishu_bitable_app_table_record | batch_delete | app_token, table_id, record_ids | - |
| 创建字段 | feishu_bitable_app_table_field | create | app_token, table_id, field_name, type | property |
| 修改字段 | feishu_bitable_app_table_field | update | app_token, table_id, field_id | field_name, type, property |
| 删除字段 | feishu_bitable_app_table_field | delete | app_token, table_id, field_id | - |
| 创建视图 | feishu_bitable_app_table_view | create | app_token, table_id, view_name, view_type | - |

## 字段值格式（易错重点）

**强制流程**：写记录前，先调用 `feishu_bitable_app_table_field.list` 获取字段的 `type` 和 `ui_type`，然后按下表构造值。

| type | ui_type | 字段类型 | 正确格式 | 常见错误 |
|------|---------|----------|---------|---------|
| 1 | Text | 文本 | `"字符串"` | — |
| 2 | Number | 数字 | `123.45` | 传字符串 |
| 3 | SingleSelect | 单选 | `"选项名"` | 传数组 `["选项名"]` |
| 4 | MultiSelect | 多选 | `["选项1", "选项2"]` | 传字符串 |
| 5 | DateTime | 日期 | `1674206443000`（毫秒） | 传秒时间戳或字符串 |
| 7 | Checkbox | 复选框 | `true` / `false` | 传字符串 |
| 11 | User | 人员 | `[{id: "ou_xxx"}]` | 传字符串或 `{name: "张三"}` |
| 15 | Url | 超链接 | `{link: "...", text: "..."}` | 只传字符串 URL |
| 17 | Attachment | 附件 | `[{file_token: "..."}]` | 传外部 URL |

## 筛选查询

```json
{
  "action": "list",
  "app_token": "S404b...",
  "table_id": "tbl...",
  "filter": {
    "conjunction": "and",
    "conditions": [
      {
        "field_name": "状态",
        "operator": "is",
        "value": ["进行中"]
      },
      {
        "field_name": "截止日期",
        "operator": "isLess",
        "value": ["ExactDate", "1740441600000"]
      }
    ]
  },
  "sort": [{"field_name": "截止日期", "desc": false}]
}
```

**筛选 operator：**

| operator | 含义 | value 要求 |
|----------|------|-----------|
| `is` | 等于 | 单个值 |
| `isNot` | 不等于 | 单个值 |
| `contains` | 包含 | 可多个值 |
| `doesNotContain` | 不包含 | 可多个值 |
| `isEmpty` | 为空 | **必须为 `[]`** |
| `isNotEmpty` | 不为空 | **必须为 `[]`** |
| `isGreater` | 大于 | 单个值 |
| `isLess` | 小于 | 单个值 |

**日期特殊值**: `["Today"]`, `["Tomorrow"]`, `["ExactDate", "时间戳"]`

## 批量操作要点

- 单次上限 **500 条**，超过需分批
- 同一数据表**不支持并发写**，串行调用 + 延迟 0.5-1 秒
- 批量操作是**原子性**的（全部成功或全部失败）

---

# 三、通用参考

## 字段选型指南

| 分类 | 字段 | 要点 |
|------|------|------|
| 录入信息 | 文本(1)、数字(2)、日期(5)、电话(13)、超链接(15)、附件(17) | 按信息本质选 |
| 分类标记 | 单选(3)、多选(4)、复选框(7) | **单选是灵魂字段** — 看板/仪表盘/自动化都靠它 |
| 跨表联动 | 双向关联(21)、单向关联(18) | 先关联，再引用 |
| 自动计算 | 公式(20) | 创建占位，文档中提供表达式 |

## 公式速查

| 模式 | 公式 | 场景 |
|------|------|------|
| 跨表求和 | `[表].FILTER(CurrentValue.[字段]=[字段]).[字段].SUM()` | 按人/类别汇总 |
| 条件计数 | `[表].COUNTIF(CurrentValue.[状态]="已完成")` | 统计数量 |
| 日期差 | `DATEDIF([开始],[截止],"D")` | 工期/逾期天数 |
| 逾期预警 | `IF([截止日期]<TODAY(),"已逾期","正常")` | 状态标记 |

公式字段 API 不支持设表达式，在文档中提供，用户手动填写。
完整速查见 [references/formula-reference.md](references/formula-reference.md)。

## 常见错误排查

| 错误码 | 现象 | 解决方案 |
|--------|------|---------|
| 1254064 | 日期字段转换失败 | 必须用毫秒时间戳，不能用字符串 |
| 1254068 | 超链接字段转换失败 | 必须用对象 `{text, link}`，不能直接传 URL |
| 1254066 | 人员字段转换失败 | 必须传 `[{id: "ou_xxx"}]` |
| 1254015 | 字段类型不匹配 | 先 list 字段，按类型构造正确格式 |
| 1254104 | 批量超限 | 分批调用，每批 ≤ 500 |
| 1254291 | 写冲突 | 串行调用 + 延迟 0.5-1 秒 |
| 1254045 | 字段名不存在 | 检查字段名（包括空格、大小写） |

## 资源限制

| 限制项 | 上限 |
|--------|------|
| 数据表 + 仪表盘 | 100（单个 App） |
| 记录数 | 20,000（单个数据表） |
| 字段数 | 300（单个数据表） |
| 视图数 | 200（单个数据表） |
| 批量操作 | 500（单次 API） |

---

## 参考文档

飞书插件自带参考（字段 property、记录值格式、完整示例）：
- `feishu-bitable/references/field-properties.md`
- `feishu-bitable/references/record-values.md`
- `feishu-bitable/references/examples.md`

本技能补充：
- [实战模式库](references/system-patterns.md) — 4 套典型系统表结构
- [公式速查](references/formula-reference.md)
- [自动化 vs 工作流](references/automation-workflow.md)
- [权限设计](references/permissions-guide.md)
- [扩展类型映射](references/field-type-mapping.md)
