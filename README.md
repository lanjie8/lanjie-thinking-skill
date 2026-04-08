# lanjie-thinking-skill

一个可复用的 Codex Skill：在对话中镜像“硅基世界里的兰洁”思维方式，提供结论先行、系统化拆解、可执行推进方案。

## 能力概览

- 结论先行：先给判断，再给依据和行动
- 第一性原理：区分事实、假设、叙事与不确定性
- 系统思维：识别杠杆点、瓶颈、反馈回路和二阶效应
- 业务导向：以结果与闭环为中心，而不是停留在工具层
- 可落地输出：给出明确动作、风险对冲和复盘检查点

## 目录结构

```text
lanjie-thinking-skill/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CHANGELOG.md
├── scripts/
│   ├── install.sh
│   └── uninstall.sh
├── examples/
│   └── prompts.md
└── skill/
    └── lanjie-thinking-skill/
        ├── SKILL.md
        ├── agents/openai.yaml
        └── references/lanjie-persona.md
```

## 安装

### 方式一：克隆后安装（推荐）

```bash
git clone https://github.com/lanjie8/lanjie-thinking-skill.git
cd lanjie-thinking-skill
bash scripts/install.sh
```

### 方式二：手动安装

```bash
TARGET="${CODEX_HOME:-$HOME/.codex}/skills/lanjie-thinking-skill"
mkdir -p "$(dirname "$TARGET")"
cp -R skill/lanjie-thinking-skill "$TARGET"
```

安装后可在 Codex 中通过相关触发语句启用该技能。

## 卸载

```bash
bash scripts/uninstall.sh
```

## 触发示例

见 [examples/prompts.md](examples/prompts.md)。

## 自定义

如果你要让技能更像你自己：

1. 修改 `skill/lanjie-thinking-skill/references/lanjie-persona.md`
2. 增加你常用表达、判断偏好、业务语境和反模式
3. 保持规则“具体、可验证、可执行”

## 校验

```bash
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" skill/lanjie-thinking-skill
```

## 许可证

本项目使用 MIT 许可证，见 [LICENSE](LICENSE)。
