#!/usr/bin/env zsh
# ═══════════════════════════════════════════════════════════
# 飞书多维表格技能 — 一键安装器
# ═══════════════════════════════════════════════════════════
#
# 两种安装方式：
#
#   方式 1 — 远程安装（推荐分享给他人）:
#     zsh <(curl -fsSL https://raw.githubusercontent.com/Larkin0302/feishu-bitable-skill/main/install.sh)
#
#   方式 2 — 本地安装（clone 后执行）:
#     git clone https://github.com/Larkin0302/feishu-bitable-skill ~/.openclaw/skills/feishu-bitable
#     zsh ~/.openclaw/skills/feishu-bitable/install.sh
#
set -euo pipefail

# ─── 捕获脚本路径（必须在函数定义之前）────────────────────
SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"

# ─── 常量 ────────────────────────────────────────────────
SKILL_NAME="feishu-bitable"
SKILL_DST="$HOME/.openclaw/skills/$SKILL_NAME"
PLUGIN_SPEC="@larksuiteoapi/feishu-openclaw-plugin"
PLUGIN_ID="feishu-openclaw-plugin"
STOCK_PLUGIN_ID="feishu"
REPO_URL="${FEISHU_BITABLE_REPO:-https://github.com/Larkin0302/feishu-bitable-skill.git}"

# ─── 颜色 ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo "${GREEN}✓${NC} $1"; }
warn() { echo "${YELLOW}⚠${NC} $1"; }
fail() { echo "${RED}✗${NC} $1"; }
info() { echo "${CYAN}→${NC} $1"; }

# ─── 辅助：读 openclaw.json ──────────────────────────────
_check_config() {
    python3 -c "
import json, sys
try:
    with open('$HOME/.openclaw/openclaw.json') as f:
        cfg = json.load(f)
except:
    print('no_config'); sys.exit(0)
plugins = cfg.get('plugins', {})
q = sys.argv[1]
if q == 'plugin_installed':
    print('yes' if sys.argv[2] in plugins.get('installs', {}) else 'no')
elif q == 'plugin_enabled':
    print('yes' if plugins.get('entries', {}).get(sys.argv[2], {}).get('enabled', True) else 'no')
elif q == 'has_credentials':
    f = cfg.get('channels', {}).get('feishu', {})
    print('yes' if f.get('appId') and f.get('appSecret') else 'no')
" "$@" 2>/dev/null
}

# ─── 判断运行模式 ────────────────────────────────────────
detect_mode() {
    # 判断是否在技能目录内运行（本地模式）
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/SKILL.md" ]; then
        SKILL_SRC="$SCRIPT_DIR"
        MODE="local"
    elif [ -f "$(pwd)/SKILL.md" ]; then
        SKILL_SRC="$(pwd)"
        MODE="local"
    else
        MODE="remote"
    fi
}

# ─── 步骤 1: 部署技能文件 ────────────────────────────────
deploy_skill() {
    echo ""
    echo "${BOLD}[1/4] 部署 feishu-bitable 技能${NC}"
    echo ""

    if [ "$MODE" = "local" ]; then
        # 本地模式：从 repo 目录复制到 ~/.openclaw/skills/
        if [ "$SKILL_SRC" = "$SKILL_DST" ]; then
            ok "技能已在目标位置，无需复制"
        else
            mkdir -p "$HOME/.openclaw/skills"
            [ -d "$SKILL_DST" ] && rm -rf "$SKILL_DST"
            cp -R "$SKILL_SRC" "$SKILL_DST"
            ok "技能已部署到 $SKILL_DST"
        fi
    else
        # 远程模式：git clone
        if ! command -v git &>/dev/null; then
            fail "git 未安装，无法远程安装"
            exit 1
        fi
        mkdir -p "$HOME/.openclaw/skills"
        if [ -d "$SKILL_DST" ]; then
            info "更新已有技能..."
            (cd "$SKILL_DST" && git pull --ff-only 2>/dev/null) && ok "技能已更新" || {
                warn "git pull 失败，重新 clone"
                rm -rf "$SKILL_DST"
                git clone "$REPO_URL" "$SKILL_DST"
                ok "技能已重新部署"
            }
        else
            info "从 $REPO_URL clone..."
            git clone "$REPO_URL" "$SKILL_DST"
            ok "技能已部署"
        fi
    fi

    # 验证关键文件
    local missing=0
    for f in SKILL.md scripts/create_bitable_template.py scripts/feishu_common.py; do
        if [ ! -f "$SKILL_DST/$f" ]; then
            fail "缺少文件: $f"
            missing=1
        fi
    done
    [ $missing -eq 0 ] && ok "关键文件验证通过"
}

# ─── 步骤 2: 安装飞书官方插件 ────────────────────────────
install_plugin() {
    echo ""
    echo "${BOLD}[2/4] 安装飞书官方插件${NC}"
    echo ""

    if ! command -v openclaw &>/dev/null; then
        fail "openclaw 未安装，跳过插件安装"
        warn "请先安装 OpenClaw: https://openclaw.com"
        return 0
    fi

    local installed=$(_check_config plugin_installed "$PLUGIN_ID")
    if [ "$installed" = "yes" ]; then
        ok "飞书官方插件已安装"
        openclaw plugins enable "$PLUGIN_ID" &>/dev/null || true
    else
        info "安装 $PLUGIN_SPEC ..."
        if openclaw plugins install "$PLUGIN_SPEC" 2>&1 | tail -5; then
            ok "飞书官方插件安装成功"
        else
            fail "安装失败，请手动执行: openclaw plugins install $PLUGIN_SPEC"
        fi
    fi
}

# ─── 步骤 3: 配置工具策略（屏蔽 App 级创建）─────────────
configure_tools() {
    echo ""
    echo "${BOLD}[3/4] 配置工具策略${NC}"
    echo ""

    local CONFIG="$HOME/.openclaw/openclaw.json"
    if [ ! -f "$CONFIG" ]; then
        warn "openclaw.json 不存在，跳过"
        return 0
    fi

    # 用 Python 安全地修改 JSON 配置
    python3 -c "
import json, sys

config_path = '$CONFIG'
DENY_TOOL = 'feishu_bitable_app'

with open(config_path, 'r') as f:
    cfg = json.load(f)

# 确保 tools.deny 存在且包含目标工具
tools = cfg.setdefault('tools', {})
deny = tools.setdefault('deny', [])
if DENY_TOOL not in deny:
    deny.append(DENY_TOOL)
    with open(config_path, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print('added')
else:
    print('exists')
" 2>/dev/null

    local result=$?
    if [ $result -eq 0 ]; then
        ok "已屏蔽 feishu_bitable_app 工具（防止 API 创建带默认字段）"
        info "保留的插件工具: record / field / view / table（日常 CRUD 不受影响）"
    else
        warn "配置失败，请手动在 openclaw.json 中添加: \"tools\": {\"deny\": [\"feishu_bitable_app\"]}"
    fi
}

# ─── 步骤 4: 禁用 stock 插件 + 检查依赖 ─────────────────
finalize() {
    echo ""
    echo "${BOLD}[4/4] 环境配置${NC}"
    echo ""

    # 禁用 stock feishu 插件
    if command -v openclaw &>/dev/null; then
        openclaw plugins disable "$STOCK_PLUGIN_ID" &>/dev/null && ok "Stock feishu 插件已禁用" || {
            # 手动修改配置
            python3 -c "
import json
config_path = '$HOME/.openclaw/openclaw.json'
try:
    with open(config_path, 'r') as f:
        cfg = json.load(f)
    cfg.setdefault('plugins', {}).setdefault('entries', {})['$STOCK_PLUGIN_ID'] = {'enabled': False}
    with open(config_path, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print('done')
except: pass
" 2>/dev/null && ok "Stock feishu 插件已通过配置禁用" || warn "跳过（可手动禁用）"
        }
    fi

    # 检查 Python requests
    if python3 -c "import requests" 2>/dev/null; then
        ok "Python requests: 已安装"
    else
        info "安装 Python requests..."
        pip3 install requests 2>/dev/null && ok "requests 安装成功" || warn "请手动安装: pip3 install requests"
    fi

    # 检查凭据
    local has_creds=$(_check_config has_credentials)
    if [ "$has_creds" = "yes" ]; then
        ok "飞书凭据: 已配置"
    else
        warn "飞书凭据未配置"
        echo ""
        echo "  请在 ~/.openclaw/openclaw.json 中配置:"
        echo ""
        echo "    \"channels\": {"
        echo "      \"feishu\": {"
        echo "        \"appId\": \"你的飞书应用 App ID\","
        echo "        \"appSecret\": \"你的飞书应用 App Secret\""
        echo "      }"
        echo "    }"
        echo ""
    fi
}

# ─── 状态报告 ────────────────────────────────────────────
report() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo ""
    ok "安装完成！"
    echo ""
    echo "  使用方式："
    echo "    在飞书中对 AI 说「搭建多维表格」→ 从零搭建系统"
    echo "    在飞书中对 AI 说「查记录」「导入数据」→ 日常 CRUD"
    echo ""

    if [ "$(_check_config has_credentials)" != "yes" ]; then
        echo "  ${YELLOW}⚠ 还需配置飞书凭据才能使用${NC}"
        echo ""
    fi

    if command -v openclaw &>/dev/null; then
        echo "  重启 gateway 使配置生效："
        echo "    openclaw gateway restart"
        echo ""
    fi
}

# ─── 主流程 ──────────────────────────────────────────────
main() {
    echo ""
    echo "╔═══════════════════════════════════════════╗"
    echo "║   飞书多维表格技能 — 一键安装器           ║"
    echo "╚═══════════════════════════════════════════╝"

    # 前置检查
    if ! command -v python3 &>/dev/null; then
        fail "python3 未安装"
        exit 1
    fi

    detect_mode
    info "安装模式: $MODE"

    deploy_skill
    install_plugin
    configure_tools
    finalize
    report
}

main "$@"
