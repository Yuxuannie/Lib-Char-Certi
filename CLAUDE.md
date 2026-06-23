# CLAUDE.md — Lib-Char-Certi

本文件是 Claude Code 在本 repo 工作的指令。开始任何操作前先确认理解项目定位、架构状态和 Git 工作流约束。

---

## 1. 项目定位

**Lib-Char-Certi** 是 standard cell library characterization 的**独立认证工具**,与 `lib_char_auto`(由 Madhuri 维护)**平行**,不是 lib_char_auto 的子模块或下游。

核心职责:对 Monte Carlo 仿真结果与 library characterization 数据进行统计验证,产出 PR(Pass Rate / Process Range)表和 waiver 报告。

包名:`cert_data_process`(`pyproject.toml` 注册的 console script 入口)。

## 2. 架构现状(关键!)

**本 repo 处于 legacy → new package 迁移阶段,两套结构并存。任何改动前先确认动的是哪一侧。**

### 2.1 新包(优先开发)

```
cert_data_process/
├── cli.py               # CLI 入口,materialize output tree + 调度 stages
├── config.py            # CertDataProcessConfig (frozen dataclass)
├── parsers/             # fmc_log, full_mc_report, summary_csv, arc_dir_name
├── stages/              # fmc_combine_data, full_mc_parse_and_normalize,
│                        # lib_join_sigma, get_pr_sigma, get_pr_moments, pr_web_app
├── analysis/            # consolidate, outliers, perarc, plots, waivers, common
├── app/                 # Tkinter 桌面 console(主入口 python -m cert_data_process.app)
├── runtime/             # 运行/会话数据层 + 无 Tk 的 HTTP fallback(原 web/,已重命名)
│                        #   runs / summary / executor / server / __main__
├── engines/             # 收进包的 live legacy 引擎(运行时正本,见下)
│   ├── combine/         #   Combine_FMC_and_{CDNS,SNPS}_lib.py + run_ldbx.tcl
│   └── get_pr/{Sigma,Moments}/   # check_sigma_with_waivers.py / check_moments_from_fmc.py
├── web_assets/          # certi_console.html(HTML dashboard 模板,原 gui/)
└── demo_run/            # 自带 demo 批次(python -m cert_data_process.app --demo)
```

- v1.0 已交付:桌面 app 主入口,sigma/moments PR + outlier 钻取 + waiver1/2 全通。
- `cli.py:PLANNED_STAGE_STATUS` 列出每个 stage 的 `implemented` 状态——动 stage 前先读这个表。
- **stage 仍 shell-out 到引擎,但引擎已收进包**:`stages/lib_join_sigma.py` → `engines/combine/`,
  `stages/get_pr_sigma.py` → `engines/get_pr/Sigma/`,`stages/get_pr_moments.py` → `engines/get_pr/Moments/`。
  这些是 `archive/2-data_process/` 原件的运行时正本副本;**改运行时行为请改 `engines/` 下的,不是 `archive/2-data_process/`**。
  真实跑批需要 pandas/numpy(combine 还需 EDA 的 `ldbx`)。

### 2.2 Legacy 树(参考标准,不要随便删)

**已归档到 `archive/`**(顶层不再平铺,避免与 active 代码混淆;`.gitattributes` 里
`archive/ export-ignore`,不进交付包)。运行时正本已收进 `cert_data_process/engines/`。

```
archive/
├── 1-Parse/                # 解析脚本 (.py + .sh)
├── ROADMAP.md              # 早期重构路线图
└── 2-data_process/
    ├── Combine_Lib_and_FMC/    # lib + FMC 合并 (CDNS/SNPS 分版本)
    ├── Combine_data/           # calculate.py 是新包 fmc_combine_data 的逻辑参考实现
    ├── Validate_CI/            # ci_validation.py
    ├── Plot/
    └── get_PR/                 # Moments/ 和 Sigma/ 各自 check_*.py + with_waivers 变体
                                # 此目录有自己的 CLAUDE.md,描述 legacy waiver 系统
```

### 2.3 输出正确性(已取消 byte-equal 硬约束)

**2026-05 更新**:用户已**取消 byte-identical 硬约束**。验收标准改为 **PR(pass rate)结果合理且正确**,用户用已知的对照 pass-rate 值来验证。

- 数值表达可因 Python 版本/平台不同而有差异,**不再要求与 legacy 脚本字节级一致**。
- `scripts/compare_*_byte_equal.py` 与 `tests/` 里的 byte-equal 测试仅作回归参考,不是验收门槛。
- 逻辑仍应对齐 legacy 参考实现(`Combine_data/calculate.py` 等),改动时优先保证 pass-rate 正确。

**Claude Code 规则**:改 stage / 判定逻辑时,关注点是"pass rate 是否正确合理",不再是"会不会破坏 byte-equal"。

## 3. 数据流与上下游

```
[stdcell char flow] → lib join → [Lib-Char-Certi] → [Voltage Margin (analysis tool)]
                                       │
                                       ├─→ base_PR        (本 repo 产出)
                                       ├─→ waiver_1 PR    (本 repo 产出)
                                       └─→ abs_tol        (waiver_2, 用户提供)
```

### 关键概念区分(写代码、注释、commit、文档时务必准确)

| 名称 | 是什么 | 与本 repo 的关系 |
|------|--------|------------------|
| **AVM** (Adaptive Voltage Model) | Cadence 的一个具体 recipe 认证项目 | 与 Lib-Char-Certi 同层,**不是** Voltage Margin |
| **Voltage Margin** | 独立的 analysis tool | 消费本 repo 的 lib join 输出,处理 waiver_3 |
| **Lib-Char-Certi** | 本 repo | 产出 base_PR 和 waiver_1 |

**绝不混用 AVM 和 Voltage Margin。** 这两个东西经常被外部混淆,代码和文档里必须区分清楚。

### Waiver 术语(存在不一致,需注意 scope)

本 repo 对 "waiver_N" 有两套并行用法,根据上下文区分:

**A. 整体 cert flow 层级(用户口径,跨工具)**

| 阶段 | 产出 | 来源 |
|------|------|------|
| PR Stage | `base_PR` | Lib-Char-Certi 自动生成 |
| Waiver 1 | `waiver_1` PR | Lib-Char-Certi 自动生成(含所有 in-tool 修正) |
| Waiver 2 | `abs_tol` | **用户查询并提供数据,不能自动推断或编造** |
| Waiver 3 | (Voltage Margin 处理) | 不在本 repo 范围 |

**B. Legacy `get_PR/` 实现层级(`archive/2-data_process/get_PR/CLAUDE.md` 口径)**

在 `check_*_with_waivers.py` 代码内部:
- `Waiver1_CI_Enlarged` 列 = CI bounds 扩张 6%
- `Waiver2_Optimistic_Only` 列 = 仅 optimistic 错误(`lib_value < mc_value`)
- 这两个都是 A 层级 `waiver_1` 的具体实现技术,**不是** A 层级的 waiver_2

**Claude Code 规则**:讨论 waiver 时先问清楚是哪一层级。涉及 `abs_tol` 时如果没有用户提供的数值,停下来明确索要,不要使用占位值。

## 4. 当前任务上下文

分支基线:`codex/investigate-silent-failure-in-logs-qvw1ci`(已合并为 main 唯一分支)。

当前焦点:debug **silent failure** — log 中未触发 error 但实际行为异常。

可能的切入点(stage 级别的 logging 都走 `[stage_name] status (reason)` 格式,见 `cli.py:_announce_stage`):
- `stages/*.py` 里的 `log_lines.append("failure=...")` 模式
- `run_manifest.json` 中的 `stage_execution` 数组
- `compatibility_report.json` 中的 `stage_reports`

如果 silent failure 的根因是 `result_obj.failed` 没正确反映 stage 内部错误,沿 `_record_stage` → `result_obj.stage_execution["status"]` 追查 status 传播链路。

## 5. Git 工作流(强约束)

用户在 git 上不熟练,以下规则严格执行,不要为了"省事"跳过。

### 5.1 强制规则

1. **绝不在 `main` 上直接修改**。任何 code change 前先创建分支:
   ```
   git checkout -b <type>/<short-desc>
   ```
   `<type>` 用 `debug` / `fix` / `investigate` / `refactor` / `test` / `feat`。

2. **以下操作执行前必须先口头确认**,展示命令和预期效果,等用户回复"yes / 确认 / 继续"再执行:
   - `git push`(任何形式,包括 `--force` / `-f`)
   - `git reset --hard`
   - `git rebase`
   - `git merge`
   - `git branch -D` / `git push origin --delete`
   - 任何会修改已 push 历史的操作

3. **commit 前永远先**:
   ```
   git status
   git diff   # 或 git diff --staged
   ```
   让用户看到改了什么,再决定 stage 和 commit。

4. **commit message 格式**:`<type>: <动词开头描述>`,英文或中文均可,不带 emoji,不带 "Generated with Claude Code" / "Co-Authored-By: Claude" 类水印。

### 5.2 冲突处理(用户核心痛点)

当 `git pull` / `git merge` / `git push` / `git rebase` 报冲突时:

1. **立刻停止**,不要自动调用 `git checkout --theirs/--ours`、`git rebase --skip`,也不要直接编辑冲突文件去"修一下"。
2. 向用户说明三件事:
   - 哪个文件冲突
   - 本地版本和远程版本各是什么(用 `git diff` 或读冲突标记 `<<<<<<<` / `=======` / `>>>>>>>`)
   - 为什么会冲突(通常是本地和远程并行修改了同一段)
3. 给出 2–3 个明确选项,说明每个的后果:
   - A. 保留本地版本(`git checkout --ours <file>`)→ 丢失远程那次改动
   - B. 接受远程版本(`git checkout --theirs <file>`)→ 丢失本地那次改动
   - C. 手动合并(由用户在编辑器里选取要保留的行)
4. 等用户选,选完执行,执行后再 `git status` 确认状态干净。

### 5.3 教学模式(用户明确要求)

用户希望在操作中学习 git。规则:

- **执行 git 命令前**:用一句话说明这条命令在做什么、为什么现在做。
- **执行后**:如果输出非平凡(分叉、多个 staged/unstaged 区段、detached HEAD、merge state 等),用 1–2 句指出关键信息。
- **避免**:长篇教程、把每个无足轻重的 `git status` 都展开讲、堆砌 git 内部原理。点到为止,用户追问再展开。

示例:

> 现在跑 `git checkout -b debug/null-deref-in-join`——从当前分支(main)派生新分支并切过去。之后的 commit 都落在新分支上,main 保持干净,万一改坏了可以直接丢分支。

> `git status` 显示 `Changes not staged for commit`,意思是这些改动 git 看到了,但还没加入下次 commit。下一步要么 `git add` 把想要的部分加入,要么 `git checkout -- <file>` 丢弃。

## 6. 代码风格与项目惯例

### 6.1 Python 基础

- 版本:**Python 3.9+**(`pyproject.toml` 锁定)
- 新模块首行 `from __future__ import annotations`
- 类型注解充分使用:`Optional` / `Iterable` / `Tuple` from `typing`,可与 PEP 604 风格混用
- 数据载体用 `@dataclass(frozen=True)`,配 `to_*_dict()` 方法做序列化(参考 `config.py:CertDataProcessConfig`)
- 模块顶部必须有 docstring 说明"这模块在 pipeline 里做什么";若涉及 legacy 兼容,写明 byte-compatibility 假设
- 错误处理:CLI 用 `parser.error(str(exc))` 退出码 2;stage 用 `result_obj.failed` 数据流向上传播,不抛裸异常

### 6.2 Stage 接口约定

每个 stage 函数返回 `XxxResult` dataclass(参考 `stages/get_pr_sigma.py:PrTableResult`):
- `stage_execution: dict` — 进 `run_manifest.json` 的 `stage_execution` 数组
- `compatibility_stage_report: dict` — 进 `compatibility_report.json`
- `failed: bool` property — `cli.py:_record_stage` 用来决定 overall exit code

Status 字符串约定:`"passed"` / `"failed"` / `"skipped"`。Reason 用小写 snake_case(如 `"missing_check_sigma_script"`、`"requires_fmc_inputs"`)。

### 6.3 Stage logging 格式

控制台:`[stage_name] status (reason)` —— 由 `cli.py:_announce_stage` 生成。

每个 stage 自带的 log 文件写到 `output_dir/logs/<stage>.log`,内容为 `key=value` 行式,便于 grep。失败时 stage 内通过 `log_lines.append("failure=...")` 追加,再回写。

### 6.4 测试(pytest)

- 框架:`pytest`(目前未在 `pyproject.toml` 声明 dev dep,但 `tests/` 直接用)
- Fixture 模式:用 `tmp_path` + 在 test 内 inline 写最小 input 文件(见 `test_cli_skeleton.py:_write_hold_fixture`);复杂场景走 `tests/fixtures/`
- byte-equal 已非验收门槛(见 §2.3);旧的 `expected/*.csv` 回归 fixture 可保留作参考,但通过与否以 pass-rate 正确性为准
- 运行:
  ```bash
  pytest tests/
  # EDA 环境无 PyPI 时:
  PYTHONPATH=. pytest tests/
  ```

### 6.5 Shell / 其他脚本

- legacy `*.sh` / `*.csh` 在 `archive/1-Parse/` 和 `archive/2-data_process/` 都存在,迁移到新包时不要破坏现存调用方
- legacy `*.tcl`(如 `run_ldbx.tcl`)是 EDA 工具 driver,通常不需要动

### 6.6 不要清理的"看起来像 dead code"的东西

- `archive/1-Parse/` 和 `archive/2-data_process/` 下的所有 legacy 脚本——它们是逻辑参考实现
- `archive/2-data_process/get_PR/` 下的 `.rpt` 文件——回归/调试时需要它们做 input
- `archive/2-data_process/get_PR/CLAUDE.md`——legacy waiver 系统的权威描述
- `check_moments_original_backup.py`——明显的 backup,但删除前先问用户

## 7. 与 Voltage Margin 项目的未来集成

预期 Lib-Char-Certi 的输出会作为 Voltage Margin 的直接输入。集成原则:

- **接口契约优先**:用稳定的文件格式 / schema 对接,不直接 cross-import 代码
- **schema 变更要走流程**:任何输出格式调整,先和 Voltage Margin 侧确认,记录在 `CHANGELOG.md` 或 release note 里
- **两个 repo 独立 versioning**:用 git tag(如 `v0.3.0`)对齐集成测试基线,不要用 commit hash 做长期依赖锚点
- **避免循环依赖**:Voltage Margin 消费本 repo 的产出,本 repo 不应反向依赖 Voltage Margin

## 8. 不要做的事(快速 checklist)

- ❌ 把 AVM 和 Voltage Margin 混为一谈
- ❌ 自动生成 / 占位 / 推断 `abs_tol` 数值
- ❌ 没有用户确认就 `git push`、`reset --hard`、`rebase`、`merge`
- ❌ 在 main 上直接 commit
- ❌ commit message 带 emoji 或 "Generated by Claude" 水印
- ❌ 自动解决 merge conflict
- ❌ rebase 已经 push 到远程的 commit
- ❌ 改判定逻辑后不核对 pass-rate 是否合理(对照用户已知值)
- ❌ 在不区分 "整体 cert flow 的 waiver_N" 和 "legacy get_PR 实现的 Waiver1/Waiver2" 的前提下讨论 waiver
- ❌ 在没问的情况下删 legacy `archive/1-Parse/` 和 `archive/2-data_process/` 下任何文件

---

**最后**:本文件是约束而不是建议。如果某条规则在具体场景下显得不合理,先停下来和用户讨论是否要修改本文件,而不是默默绕过。
