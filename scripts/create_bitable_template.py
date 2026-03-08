#!/usr/bin/env python3
"""
飞书多维表格模板自动搭建脚本
=============================
为《飞书多维表格·从零到一》课程自动创建练习模板。

功能：
  1. 创建新的多维表格应用（独立 bitable 或知识库节点）
  2. 支持多张数据表（第一张复用默认表，后续表通过 API 创建）
  3. 每张表独立配置：首字段名 + 自定义字段 + 默认视图重命名 + 示例数据 + 视图
  4. 自动清理默认字段和空行
  5. 设置管理员权限

用法：
  # 内置配置模式（向后兼容）
  python create_bitable_template.py                           # 创建第1课模板
  python create_bitable_template.py --lesson 1                # 同上
  python create_bitable_template.py --lesson 1 --wiki         # 创建到知识库
  python create_bitable_template.py --dry-run                 # 只打印计划

  # JSON 配置模式（推荐）
  python create_bitable_template.py --config template.json              # 从 JSON 创建
  python create_bitable_template.py --config template.json --wiki       # 创建到知识库
  python create_bitable_template.py --config template.json --dry-run    # 预览计划

JSON 配置格式（多表）：
  {
    "app_name": "第N课·标题",
    "tables": [
      {
        "name": "数据表1",
        "first_field_name": "首字段名",
        "default_view_name": "全部数据",
        "fields": [...],
        "views": [...],
        "records": [...]
      },
      {
        "name": "数据表2",
        ...
      }
    ]
  }

  也兼容单表格式（"table" 代替 "tables"）。

依赖：
  - feishu_common.py（同目录）
  - 00.系统/.env（飞书凭据）
"""

import sys
import time
import json
import argparse
from pathlib import Path

# 确保能 import 同目录的 feishu_common
sys.path.insert(0, str(Path(__file__).parent))
from feishu_common import FeishuClient, DELAY

sys.stdout.reconfigure(encoding="utf-8")

# ═══════════════════════════════════════════════════════════
# 常量配置
# ═══════════════════════════════════════════════════════════
import os

ADMIN_PHONE = os.environ.get("FEISHU_ADMIN_PHONE", "18834523581")
ADMIN_OPEN_ID = os.environ.get(
    "FEISHU_ADMIN_OPEN_ID", "ou_36479cbaab14f4cdb9a2ef095de386c1"
)

# 知识库配置（可通过命令行参数覆盖）
SPACE_ID = os.environ.get("FEISHU_WIKI_SPACE_ID", "7610609535908105159")
PARENT_NODE = os.environ.get("FEISHU_WIKI_PARENT_NODE", "DDOLwWnYlijfsUkKuKTcg0bonng")  # 「模板」节点

# 字段类型名称映射（用于 dry-run 显示）
FIELD_TYPE_NAMES = {
    1: "文本", 2: "数字", 3: "单选", 4: "多选", 5: "日期",
    7: "复选框", 11: "人员", 13: "电话", 15: "超链接", 17: "附件",
    99001: "货币", 99002: "评分", 99003: "进度", 99004: "邮箱",
}

# 99xxx extended field types -> (base_type, ui_type) mapping
# Feishu API requires splitting into base type + ui_type for creation
UI_TYPE_MAP = {
    99001: (2, "Currency"),
    99002: (2, "Rating"),
    99003: (2, "Progress"),
    99004: (1, "Email"),
}


# ═══════════════════════════════════════════════════════════
# 第 1 课模板配置（内置，向后兼容）
# ═══════════════════════════════════════════════════════════

LESSON_01_CONFIG = {
    "app_name": "第1课·客户数据对比体验表",
    "tables": [
        {
            "name": "客户信息",
            "first_field_name": "客户姓名",
            "default_view_name": "全部数据",
            "fields": [
                {"field_name": "公司", "type": 1},
                {
                    "field_name": "客户等级",
                    "type": 3,
                    "property": {
                        "options": [
                            {"name": "A级"},
                            {"name": "B级"},
                            {"name": "C级"},
                        ]
                    },
                },
                {
                    "field_name": "签约日期",
                    "type": 5,
                    "property": {"date_formatter": "yyyy/MM/dd"},
                },
                {"field_name": "负责人", "type": 1},
                {
                    "field_name": "合同金额",
                    "type": 2,
                    "property": {"formatter": "0.00"},
                },
                {
                    "field_name": "状态",
                    "type": 3,
                    "property": {
                        "options": [
                            {"name": "待办"},
                            {"name": "进行中"},
                            {"name": "已完成"},
                        ]
                    },
                },
            ],
            "views": [
                {"view_name": "按等级看板", "view_type": "kanban"},
                {"view_name": "签约日历", "view_type": "calendar"},
            ],
            "records": [
                {"客户姓名": "张伟", "公司": "星辰科技", "客户等级": "A级", "签约日期": 1736006400000, "负责人": "李明", "合同金额": 158000, "状态": "已完成"},
                {"客户姓名": "王芳", "公司": "云帆网络", "客户等级": "B级", "签约日期": 1736265600000, "负责人": "张丽", "合同金额": 86000, "状态": "已完成"},
                {"客户姓名": "李强", "公司": "鼎新咨询", "客户等级": "A级", "签约日期": 1736611200000, "负责人": "李明", "合同金额": 220000, "状态": "已完成"},
                {"客户姓名": "赵敏", "公司": "汇通物流", "客户等级": "C级", "签约日期": 1736870400000, "负责人": "王磊", "合同金额": 35000, "状态": "进行中"},
                {"客户姓名": "陈浩", "公司": "蓝桥教育", "客户等级": "B级", "签约日期": 1737129600000, "负责人": "张丽", "合同金额": 92000, "状态": "已完成"},
                {"客户姓名": "刘洋", "公司": "翠微食品", "客户等级": "A级", "签约日期": 1737475200000, "负责人": "李明", "合同金额": 175000, "状态": "已完成"},
                {"客户姓名": "孙静", "公司": "明道传媒", "客户等级": "C级", "签约日期": 1737734400000, "负责人": "王磊", "合同金额": 28000, "状态": "进行中"},
                {"客户姓名": "周杰", "公司": "恒远机械", "客户等级": "B级", "签约日期": 1738339200000, "负责人": "李明", "合同金额": 110000, "状态": "进行中"},
                {"客户姓名": "吴婷", "公司": "锦绣地产", "客户等级": "A级", "签约日期": 1738684800000, "负责人": "张丽", "合同金额": 310000, "状态": "已完成"},
                {"客户姓名": "郑凯", "公司": "万象商贸", "客户等级": "B级", "签约日期": 1738944000000, "负责人": "王磊", "合同金额": 78000, "状态": "已完成"},
                {"客户姓名": "黄蕾", "公司": "创域软件", "客户等级": "C级", "签约日期": 1739289600000, "负责人": "张丽", "合同金额": 42000, "状态": "待办"},
                {"客户姓名": "林峰", "公司": "泰和医药", "客户等级": "A级", "签约日期": 1739548800000, "负责人": "李明", "合同金额": 260000, "状态": "进行中"},
                {"客户姓名": "何欣", "公司": "龙腾电子", "客户等级": "B级", "签约日期": 1739808000000, "负责人": "王磊", "合同金额": 95000, "状态": "进行中"},
                {"客户姓名": "罗琳", "公司": "嘉禾农业", "客户等级": "C级", "签约日期": 1739980800000, "负责人": "张丽", "合同金额": 31000, "状态": "待办"},
                {"客户姓名": "马超", "公司": "信达金融", "客户等级": "A级", "签约日期": 1740153600000, "负责人": "李明", "合同金额": 420000, "状态": "进行中"},
                {"客户姓名": "朱丹", "公司": "华美装饰", "客户等级": "B级", "签约日期": 1740412800000, "负责人": "王磊", "合同金额": 88000, "状态": "待办"},
                {"客户姓名": "谢晨", "公司": "博学文化", "客户等级": "A级", "签约日期": 1740672000000, "负责人": "张丽", "合同金额": 195000, "状态": "待办"},
                {"客户姓名": "韩冰", "公司": "天成建设", "客户等级": "C级", "签约日期": 1740758400000, "负责人": "李明", "合同金额": 55000, "状态": "待办"},
                {"客户姓名": "曹阳", "公司": "盛世集团", "客户等级": "B级", "签约日期": 1741104000000, "负责人": "王磊", "合同金额": 130000, "状态": "待办"},
                {"客户姓名": "冯雪", "公司": "优品零售", "客户等级": "A级", "签约日期": 1741363200000, "负责人": "张丽", "合同金额": 240000, "状态": "待办"},
            ],
        },
    ],
}

# 课程模板注册表（后续课程在此添加配置即可）
LESSON_CONFIGS = {
    1: LESSON_01_CONFIG,
}


# ═══════════════════════════════════════════════════════════
# 配置归一化
# ═══════════════════════════════════════════════════════════

def normalize_config(config: dict) -> dict:
    """将配置归一化为多表格式。

    兼容两种格式：
    - 新格式: {"tables": [{ ... }, { ... }]}
    - 旧格式: {"table": { ... }}  → 自动转为 {"tables": [{ ... }]}
    """
    if "tables" in config:
        return config
    if "table" in config:
        config = dict(config)
        config["tables"] = [config.pop("table")]
        return config
    raise ValueError("配置中缺少 'tables' 或 'table' 字段")


# ═══════════════════════════════════════════════════════════
# 模板搭建器
# ═══════════════════════════════════════════════════════════

class BitableTemplateBuilder:
    """使用飞书 API 创建多维表格练习模板。

    支持两种创建模式：
    - 独立模式：创建独立的多维表格应用
    - 知识库模式（--wiki）：在知识库「模板」节点下创建

    支持多张数据表：第一张复用默认表，后续表通过 API 新建。
    """

    def __init__(self, dry_run=False, wiki_mode=False):
        self.client = FeishuClient()
        self.dry_run = dry_run
        self.wiki_mode = wiki_mode
        self.app_token = None
        self.node_token = None  # 知识库模式下的 node_token
        # 当前正在操作的表（每张表切换时重置）
        self.table_id = None
        self.field_map = {}
        self.warnings = []  # 搭建过程中的警告（降级/失败字段等）

    def build(self, config: dict):
        """执行完整的模板搭建流程"""
        config = normalize_config(config)
        app_name = config["app_name"]
        tables_cfg = config["tables"]

        # 允许 JSON 配置中的 wiki_mode 字段（命令行 --wiki 优先）
        if not self.wiki_mode and config.get("wiki_mode"):
            self.wiki_mode = True

        mode_label = "知识库模式" if self.wiki_mode else "独立模式"

        print(f"\n{'='*60}")
        print(f"  🏗️  开始搭建模板：{app_name}")
        print(f"  📍 模式：{mode_label}")
        print(f"  📊 数据表：{len(tables_cfg)} 张")
        print(f"{'='*60}\n")

        if self.dry_run:
            self._print_plan(config)
            return

        # Step 0: 认证
        self.client.authenticate()

        # Step 1: 创建多维表格应用
        if self.wiki_mode:
            self._create_wiki_app(app_name)
        else:
            self._create_app(app_name)

        # Step 1.5: 获取默认脏表 ID（所有表创建完后删除它）
        default_table_id = self._get_default_table_id()

        # Step 2-N: 逐张搭建数据表
        # 核心策略：ALL tables use "create with fields" API
        # → 首字段直接是 type=1 文本，无默认字段，无空行
        table_results = []
        for idx, table_cfg in enumerate(tables_cfg):
            table_num = idx + 1
            table_name = table_cfg["name"]

            print(f"\n{'─'*60}")
            print(f"  📊 数据表 {table_num}/{len(tables_cfg)}：{table_name}")
            print(f"{'─'*60}")

            # 重置当前表状态
            self.table_id = None
            self.field_map = {}

            # 直接创建干净的表（含字段定义）
            first_field_name = table_cfg.get("first_field_name", "名称")
            default_view_name = table_cfg.get("default_view_name", "全部数据")
            self._create_table_with_fields(
                table_name, first_field_name,
                table_cfg.get("fields", []),
                default_view_name,
            )

            # 写入数据 + 创建视图（无需清理字段/空行）
            if table_cfg.get("records"):
                self._insert_records(table_cfg["records"])
            if table_cfg.get("views"):
                self._create_views(table_cfg["views"])

            table_results.append({
                "name": table_name,
                "table_id": self.table_id,
            })

        # 删除飞书自动创建的默认脏表
        self._delete_table(default_table_id)

        # 设置管理员
        self._set_admin()

        # 完成
        link = self._get_link()
        print(f"\n{'='*60}")
        print(f"  ✅ 模板搭建完成！")
        print(f"  📋 应用 Token: {self.app_token}")
        if self.node_token:
            print(f"  📄 节点 Token: {self.node_token}")
        print(f"  📊 数据表: {len(table_results)} 张")
        for tr in table_results:
            print(f"     - {tr['name']} ({tr['table_id']})")
        print(f"  🔗 打开链接: {link}")
        if self.warnings:
            print(f"\n  ⚠️  需手动处理的事项 ({len(self.warnings)} 项):")
            for i, w in enumerate(self.warnings, 1):
                print(f"     {i}. {w}")
        print(f"{'='*60}\n")

        # 输出结构化结果供调用方使用
        result_info = {
            "app_token": self.app_token,
            "tables": table_results,
            "link": link,
        }
        if self.node_token:
            result_info["node_token"] = self.node_token
        if self.warnings:
            result_info["warnings"] = self.warnings
        print(f"__RESULT_JSON__:{json.dumps(result_info, ensure_ascii=False)}")

    def _get_link(self):
        """根据模式返回对应的打开链接"""
        if self.wiki_mode and self.node_token:
            return f"https://vantasma.feishu.cn/wiki/{self.node_token}"
        return f"https://vantasma.feishu.cn/base/{self.app_token}"

    # ─── 创建应用 ────────────────────────────────────

    def _create_app(self, name: str):
        print(f"📦 创建多维表格应用 [{name}]（独立模式）")
        data = self.client._request(
            "POST",
            "/bitable/v1/apps",
            json={"name": name},
        )
        self.app_token = data["data"]["app"]["app_token"]
        print(f"   ✓ 创建成功，app_token = {self.app_token}")
        time.sleep(DELAY)

    def _create_wiki_app(self, name: str):
        print(f"📦 创建多维表格节点 [{name}]（知识库模式）")
        print(f"   📍 知识库: {SPACE_ID}")
        print(f"   📍 父节点: {PARENT_NODE}")
        data = self.client._request(
            "POST",
            f"/wiki/v2/spaces/{SPACE_ID}/nodes",
            json={
                "obj_type": "bitable",
                "parent_node_token": PARENT_NODE,
                "node_type": "origin",
                "title": name,
            },
        )
        node = data["data"]["node"]
        self.node_token = node["node_token"]
        self.app_token = node["obj_token"]
        print(f"   ✓ 创建成功")
        print(f"     node_token = {self.node_token}")
        print(f"     app_token  = {self.app_token}")
        time.sleep(DELAY)

    # ─── 数据表创建（新方式：带字段创建，无默认字段问题） ──

    def _get_default_table_id(self):
        """获取飞书自动创建的默认数据表 ID（后续删除用）"""
        data = self.client._get(
            f"/bitable/v1/apps/{self.app_token}/tables",
            params={"page_size": 20},
        )
        tables = data.get("data", {}).get("items", [])
        if not tables:
            raise Exception("未找到默认表")
        default_id = tables[0]["table_id"]
        print(f"   📋 默认表: {default_id}（将在所有表创建完后删除）")
        return default_id

    def _create_table_with_fields(self, table_name, first_field_name, field_configs, default_view_name="全部数据"):
        """创建数据表时直接指定字段。

        使用 POST /tables 的 fields 参数：
        - 首字段直接是 type=1（文本），不是多行文本
        - 没有飞书默认的多行文本/单选/日期/附件字段
        - 没有 10 条空白记录
        三个老大难问题一次性解决。
        """
        print(f"\n📊 创建数据表 [{table_name}]（含字段定义）")

        # 构建字段列表：首字段(type=1 文本) + 自定义字段
        fields = [{"field_name": first_field_name, "type": 1}]
        for fc in field_configs:
            field_type = fc["type"]
            if field_type in UI_TYPE_MAP:
                base_type, ui_type = UI_TYPE_MAP[field_type]
                field_def = {"field_name": fc["field_name"], "type": base_type, "ui_type": ui_type}
            else:
                field_def = {"field_name": fc["field_name"], "type": field_type}
            if "property" in fc:
                field_def["property"] = fc["property"]
            fields.append(field_def)

        payload = {
            "table": {
                "name": table_name,
                "default_view_name": default_view_name,
                "fields": fields,
            }
        }

        data = self.client._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables",
            json=payload,
        )
        self.table_id = data["data"]["table_id"]
        print(f"   ✓ table_id = {self.table_id}")
        print(f"   ✓ {len(fields)} 个字段直接创建完毕（无默认字段）")
        time.sleep(DELAY)

    def _delete_table(self, table_id):
        """删除数据表（用于清理飞书自动创建的默认脏表）"""
        print(f"\n🗑️  删除默认脏表 ({table_id})")
        try:
            self.client._request(
                "DELETE",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}",
            )
            print(f"   ✓ 已删除")
        except Exception as e:
            print(f"   ⚠ 删除失败（不影响使用）: {e}")
        time.sleep(DELAY)

    # ─── 写入数据 ────────────────────────────────────

    def _insert_records(self, records: list):
        print(f"\n📝 写入示例数据 ({len(records)} 条)")

        batch_size = 100
        total = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            payload = {
                "records": [{"fields": rec} for rec in batch]
            }
            self.client._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_create",
                json=payload,
            )
            total += len(batch)
            print(f"   ✓ 已写入 {total}/{len(records)} 条")
            time.sleep(DELAY)

    # ─── 创建视图 ────────────────────────────────────

    def _create_views(self, view_configs: list):
        print(f"\n🔭 创建视图")

        for vc in view_configs:
            vtype = vc["view_type"]

            if vtype == "calendar":
                print(f"   ⚠ {vc['view_name']} — 日历视图需手动创建（飞书 API 不支持 view_type=calendar）")
                print(f"     操作：视图栏「+」→ 日历视图 → 选择日期字段")
                continue

            payload = {
                "view_name": vc["view_name"],
                "view_type": vtype,
            }
            try:
                self.client._request(
                    "POST",
                    f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/views",
                    json=payload,
                )
                print(f"   ✓ {vc['view_name']} ({vtype})")
            except Exception as e:
                print(f"   ⚠ {vc['view_name']} 创建失败: {e}")
            time.sleep(DELAY)

    # ─── 设置管理员 ──────────────────────────────────

    def _set_admin(self):
        print(f"\n🔑 设置管理员")

        open_id = ADMIN_OPEN_ID
        if not open_id and ADMIN_PHONE:
            try:
                api_path = "/contact/v3" + "/users" + "/batch_get_id"
                data = self.client._request(
                    "POST",
                    api_path,
                    json={"mobiles": [ADMIN_PHONE]},
                    params={"user_id_type": "open_id"},
                )
                user_list = data.get("data", {}).get("user_list", [])
                if user_list:
                    open_id = user_list[0].get("user_id", "")
                    print(f"   ✓ 查到 open_id = {open_id}")
                    print(f"   💡 建议保存到 .env: FEISHU_ADMIN_OPEN_ID={open_id}")
            except Exception as e:
                print(f"   ⚠ 查询用户失败: {e}")
                print(f"   💡 请手动在飞书中添加管理员，或在 .env 中配置 FEISHU_ADMIN_OPEN_ID")
                return

        if not open_id:
            print(f"   ⚠ 无法获取管理员 open_id，跳过")
            return

        try:
            perm_path = f"/drive/v1/permissions/{self.app_token}/members"
            self.client._request(
                "POST",
                perm_path,
                params={"type": "bitable", "need_notification": "false"},
                json={
                    "member_type": "openid",
                    "member_id": open_id,
                    "perm": "full_access",
                },
            )
            print(f"   ✅ 管理员权限设置成功（full_access）")
        except Exception as e:
            print(f"   ⚠ 权限设置失败: {e}")
            print(f"   💡 请手动在飞书中添加管理员")
        time.sleep(DELAY)

    # ─── Dry Run ─────────────────────────────────────

    def _print_plan(self, config: dict):
        mode_label = "知识库模式" if self.wiki_mode else "独立模式"
        tables_cfg = config["tables"]

        print(f"🔍 DRY RUN 模式 — 以下为搭建计划，不实际执行\n")
        print(f"应用名称: {config['app_name']}")
        print(f"创建模式: {mode_label}")
        if self.wiki_mode:
            print(f"知识库 ID: {SPACE_ID}")
            print(f"父节点:    {PARENT_NODE}")
        print(f"数据表数量: {len(tables_cfg)} 张")

        total_records = 0
        total_fields = 0
        total_views = 0

        for idx, t in enumerate(tables_cfg):
            is_first = (idx == 0)
            table_num = idx + 1
            first_field_name = t.get("first_field_name", "名称")
            default_view_name = t.get("default_view_name", "全部数据")

            print(f"\n{'─'*50}")
            print(f"📊 数据表 {table_num}: {t['name']}")
            print(f"{'─'*50}")
            print(f"  创建方式: 带字段直接创建（无默认字段）")
            print(f"  首字段名: {first_field_name} (type=1 文本)")
            print(f"  默认视图名: {default_view_name}")

            fields = t.get("fields", [])
            total_fields += len(fields) + 1
            print(f"\n  字段 ({len(fields) + 1}):")
            print(f"    1. {first_field_name} [文本] (首字段)")
            for i, f in enumerate(fields, 2):
                ftype = FIELD_TYPE_NAMES.get(f["type"], f"type={f['type']}")
                opts = ""
                if f.get("property", {}).get("options"):
                    opts = " → " + "/".join(o["name"] for o in f["property"]["options"])
                print(f"    {i}. {f['field_name']} [{ftype}]{opts}")

            records = t.get("records", [])
            if records:
                total_records += len(records)
                print(f"\n  示例数据: {len(records)} 条")

            views = t.get("views", [])
            if views:
                total_views += len(views)
                print(f"\n  视图 ({len(views)} + 1 默认):")
                print(f"    - {default_view_name} (grid, 默认视图重命名)")
                for v in views:
                    manual = " ⚠ 需手动创建" if v["view_type"] == "calendar" else ""
                    print(f"    - {v['view_name']} ({v['view_type']}){manual}")

        print(f"\n{'═'*50}")
        print(f"📋 搭建总览")
        print(f"{'═'*50}")
        print(f"  数据表: {len(tables_cfg)} 张")
        print(f"  字段总数: {total_fields} 个")
        print(f"  数据总数: {total_records} 条")
        print(f"  视图总数: {total_views} + {len(tables_cfg)} 默认")

        print(f"\n搭建步骤预览:")
        print(f"  1. {'在知识库创建 bitable 节点' if self.wiki_mode else '创建独立 bitable 应用'}")
        for idx, t in enumerate(tables_cfg):
            table_num = idx + 1
            first_field_name = t.get("first_field_name", "名称")
            default_view_name = t.get("default_view_name", "全部数据")
            fields = t.get("fields", [])
            records = t.get("records", [])
            views = t.get("views", [])

            if len(tables_cfg) > 1:
                print(f"  ── 数据表 {table_num}: {t['name']} ──")

            print(f"  {table_num}a. 创建数据表 [{t['name']}]（含 {len(fields)+1} 个字段定义，无默认字段）")
            if records:
                print(f"  {table_num}b. 写入 {len(records)} 条示例数据")
            if views:
                api_views = [v for v in views if v["view_type"] != "calendar"]
                manual_views = [v for v in views if v["view_type"] == "calendar"]
                suffix = f"（{len(manual_views)} 个需手动）" if manual_views else ""
                print(f"  {table_num}c. 创建 {len(api_views)} 个视图{suffix}")

        print(f"  N. 删除飞书自动创建的默认脏表")
        print(f"  N+1. 设置管理员权限")
        print(f"\n✅ 计划生成完毕。去掉 --dry-run 参数即可实际创建。")


# ═══════════════════════════════════════════════════════════
# JSON 配置加载
# ═══════════════════════════════════════════════════════════

def load_json_config(path: str) -> dict:
    """从 JSON 文件加载模板配置"""
    p = Path(path)
    if not p.exists():
        print(f"❌ 配置文件不存在: {path}")
        sys.exit(1)

    try:
        with open(p, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        sys.exit(1)

    # 验证必需字段
    if "app_name" not in config:
        print("❌ JSON 配置缺少 'app_name' 字段")
        sys.exit(1)

    # 支持 tables（多表）或 table（单表）
    if "tables" in config:
        tables = config["tables"]
        if not isinstance(tables, list) or len(tables) == 0:
            print("❌ 'tables' 必须是非空数组")
            sys.exit(1)
    elif "table" in config:
        tables = [config["table"]]
    else:
        print("❌ JSON 配置缺少 'tables' 或 'table' 字段")
        sys.exit(1)

    # 验证每张表的必需字段
    for i, table in enumerate(tables):
        prefix = f"tables[{i}]" if len(tables) > 1 else "table"
        if "name" not in table:
            print(f"❌ {prefix} 缺少 'name' 字段")
            sys.exit(1)
        if "fields" not in table:
            print(f"❌ {prefix} 缺少 'fields' 字段")
            sys.exit(1)

    print(f"📄 已加载配置文件: {path}（{len(tables)} 张数据表）")
    return config


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="飞书多维表格课程模板自动搭建",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --lesson 1                          使用内置第1课配置创建
  %(prog)s --lesson 1 --wiki                   创建到知识库
  %(prog)s --config template.json              从 JSON 文件创建（支持多表）
  %(prog)s --config template.json --wiki       从 JSON 创建到知识库
  %(prog)s --config template.json --dry-run    预览搭建计划
        """,
    )
    parser.add_argument(
        "--lesson", "-l",
        type=int,
        default=None,
        help="课程编号（使用内置配置）",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="JSON 配置文件路径（推荐，支持多表）",
    )
    parser.add_argument(
        "--wiki", "-w",
        action="store_true",
        help="创建到知识库（而非独立 bitable）",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=None,
        help="知识库 space_id（覆盖默认值）",
    )
    parser.add_argument(
        "--parent-node",
        type=str,
        default=None,
        help="知识库父节点 node_token（覆盖默认值）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印搭建计划，不实际创建",
    )
    args = parser.parse_args()

    # 确定配置来源
    if args.config:
        config = load_json_config(args.config)
    elif args.lesson is not None:
        if args.lesson not in LESSON_CONFIGS:
            available = ", ".join(str(k) for k in sorted(LESSON_CONFIGS.keys()))
            print(f"❌ 第 {args.lesson} 课的模板配置尚未添加。")
            print(f"   当前可用: {available}")
            sys.exit(1)
        config = LESSON_CONFIGS[args.lesson]
    else:
        config = LESSON_CONFIGS[1]

    # 覆盖知识库配置
    global SPACE_ID, PARENT_NODE
    if args.space_id:
        SPACE_ID = args.space_id
    if args.parent_node:
        PARENT_NODE = args.parent_node

    builder = BitableTemplateBuilder(dry_run=args.dry_run, wiki_mode=args.wiki)
    builder.build(config)


if __name__ == "__main__":
    main()
