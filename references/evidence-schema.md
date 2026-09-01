# 证据记录字段

这些约定供内置工具使用，不要求短问答照表填。可扩展字段，不伪填记录。保存UTF-8，JSON数值必须有限；缺失值用null并解释，不写NaN或Infinity。

## project.json

`init_project.py`生成基础结构。`competition`保存当届身份、规则状态、AI活动限制和实际截止时刻；时刻采用含时区的ISO8601，例如`2026-09-27T12:00:00+08:00`。状态是事实，不是为了过审而填的开关。

`questions`中的每项：

```json
{
  "id": "Q1",
  "requirement": "从题面准确转写的交付要求",
  "depends_on": [],
  "status": "in_progress",
  "run_ids": [],
  "artifacts": [],
  "proof_artifact": null
}
```

状态可用`todo/in_progress/verified/limited`；`verified`表示已按题面验收，不等于只写完。纯理论问题可绑定`proof_artifact`而不强求无意义的实验。`limited`诚实表示未完整满足要求；提交审计会提示该缺口。

`reviews`各项用`pending/passed/failed/not_applicable`、`evidence`文件路径列表和`notes`具体解释。`passed`应指向实际核查记录；`not_applicable`须解释。工具只检查记录结构，不知道人是否真的检查过。

## 实验

命令示例（路径按宿主引用规则处理）：

```text
python <skill-dir>/scripts/run_experiment.py --project <project-dir> --id ridge-v1 --seed 42 --input data/raw/train.csv --input data/processed/split.json --input config.json --source src/main.py --output results/ridge-v1/predictions.csv --metrics results/ridge-v1/metrics.json -- python src/main.py
```

声明所有影响结果的输入、配置与源码；多个`--input/--source/--output`可重复。记录器创建日志和`runs/ridge-v1/run.json`，不会执行shell字符串。命令代码须读取`MODELING_SEED`或对应显式配置；记录种子本身不等于控制随机性。结果路径应是本次新路径，记录器拒绝复用旧结果。

`run.json`中的环境版本属于记录器的Python；MATLAB或另一个Python环境须在实际程序输出中另记真实版本。状态`completed`仅指命令成功、声明文件存在且源文件未在运行中改变，科学有效性另行验证。

## claims.json

数字型主张绑定真实原始指标值，而不是手写摘要数字。下面的0.12只说明格式，不是任何赛事结果：

```json
[
  {
    "id": "C1",
    "question_id": "Q1",
    "kind": "numeric",
    "text": "基线在留出集的MAE为0.12米",
    "run_id": "ridge-v1",
    "metric": "validation.mae",
    "value": 0.12,
    "unit": "m",
    "scope": "该留出集及当前特征可用性条件"
  }
]
```

`metric`用点分路径访问指标JSON，键名中不要用字面点号。`value`与原始值一致，显示时另做舍入。`derived/qualitative`主张用`evidence`列表绑定推导/分析文件，并保留`question_id/text/scope`。审计不会自动解析自然语言、识别论文里未登记的数值或检验推导，仍需阅读全文核对。

## sources.json

每条至少包含`id/title/locator/verification/cited`，可加作者、年份、DOI、URL、页码、访问日、使用位置和许可证。`locator`为已打开的URL、DOI或本地文件与页码；`verification`为`verified/unverified`。只有文献身份及所支撑内容实际核对后才标verified。搜索命中不够；工具仅检查登记。

## ai_usage.jsonl

一行一条实际活动：`time/tool/version/version_release_date/purpose/input_refs/output_refs/adopted/human_changes/verification`。`time`是含时区的实际时间，`input_refs/output_refs`是记录引用列表，`adopted`是布尔值，具体采用范围在`human_changes/verification`说明。未知版本信息写null并注明待核；不得补造人工贡献。日志与对外AI声明不同：先按规则脱敏和选择必要记录，再生成当届要求的说明，不自动上传原始交互。

确实没有使用AI的阶段可记录`used:false`，并填写`time/purpose/verification`说明核查范围；不得以“没有采用最终文字”为由隐瞒建模、编码或检查时的AI使用。工具只验证基本JSONL字段，竞赛额外要求的开发者、版本发布日期、实际使用日期与声明附件仍须逐项核验。

## 机械审计的范围

```text
python <skill-dir>/scripts/audit_project.py <project-dir> --stage analysis
python <skill-dir>/scripts/audit_project.py <project-dir> --stage draft --output checks/draft-01.json
python <skill-dir>/scripts/audit_project.py <project-dir> --stage submission --output checks/submission-01.json
```

退出码0表示未发现结构性错误，**仍可能有warning，且不代表论文正确/可以投稿**；1表示发现错误；2表示调用或数据格式错误。competition模式下，当届赛规、AI范围或排版模板未核验会在分析/草稿阶段尽早警告，到交稿阶段升级为错误。检查已登记问题/主张引用的运行，不要求已弃用的失败实验全部变为成功。审计关注文件是否变动、指标是否同源、必要记录是否齐全；科学判断和可视化/匿名/规则核验由人和agent实际完成。
