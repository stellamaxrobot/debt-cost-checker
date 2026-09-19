**[非商业使用许可](LICENSE.md)：** 非商业的个人、教学、研究及公益用途可免费使用；商用须事先取得书面授权。采用公开源码、非商业许可，不属于 OSI 批准的开源许可。

<div align="center">

[English](README.md) | **简体中文**

# 债务算清楚

**看懂欠谁的钱、每一笔费用，以及逾期后金额怎样变化。**

Debt Cost Checker · 中文消费借贷 · Codex Skill · Alpha

[报告示例](#报告示例) · [如何使用](#如何使用) · [适用范围](#适用范围)

</div>

把借款协议、账单和还款记录交给 Codex，获得一份简短的债务分析。资料不齐时，会说明哪些金额仍待核对，以及下一步最值得补什么。

## 报告示例

> 下方为模拟输出结构。日期、机构和金额全部虚构，仅用于展示排版，不代表真实案例或脚本实测结果。这里不展示输入材料。

### 你的欠款，现在能算清多少？

**截至 2026-09-17，当前到期金额为 8,240 元。**

| 金额口径 | 模拟结果 |
| :--- | ---: |
| 当前到期，需要处理的部分 | **8,240 元** |
| 尚未到期的计划金额 | 4,120 元 |
| 已知剩余总额：以上两项相加 | **12,360 元** |
| 其中，全部剩余本金 | 11,600 元 |
| 平台同日显示的金额 | 13,500 元 |
| 平台金额与已知剩余总额的差额 | **1,140 元，待核对** |

剩余本金已经包含在总额里，无需重复相加。提前结清时是否减免未来息费，需要另行核对。

**当前到期的 8,240 元包括：**

| 项目 | 金额 |
| :--- | ---: |
| 到期本金 | 7,600 元 |
| 正常利息 | 300 元 |
| 逾期罚息 | 140 元 |
| 担保费 | 200 元 |

**钱目前欠谁？**

A 放款机构是最后能够确认的债权人。B 担保机构提供了担保，目前没有材料证明它已代偿。C 催收服务方负责联系还款，其催收身份不能单独证明债权归属。

**需要注意什么？**

- 平台多出的 1,140 元还没有对应到具体收费项目。
- 综合年化成本示例为 31.80%，高于合同标示的 18%；需要核对附加费用。
- 债权关系仍有证据缺口，高成本提示不等于违法认定。

**先补这两项：** 平台逐项账单；担保方的代偿或债权变更证明（如对方声称已发生）。

<details>
<summary>材料不足、未来预测时，会怎样显示？</summary>

**材料不足**

“已收到的两笔还款可以核实，但还款记录是否完整仍不清楚。当前结果仅覆盖现有记录，暂不能确认实际余额。”

**未来预测**

“按截至今日已知的计费规则，列出未来 1、3、6 个月的金额。每个节点注明当前到期、未到期计划和剩余总额；假设期间没有新增还款，尚未确认的代偿、转让或收费会单独提示。”

**证据说明**

“可信度：B · 较可靠。最弱项：还款记录。债权关系的确认程度单独说明。”

</details>

## 如何使用

从本仓库的 **Code → Download ZIP** 下载并解压，将解压后的文件夹重命名为 `debt-cost-checker`，放入 `~/.codex/skills/`。开启新的 Codex 对话，附上手头材料并说：

```text
使用 $debt-cost-checker 帮我看看目前欠款由什么组成，
哪些费用需要核对，以及未来 1、3、6 个月可能变成多少。
```

只记得收到多少钱、平台显示欠多少，也可以开始。无法可靠计算的部分会保留为待确认项。

## 适用范围

| 场景 | 可以得到什么 |
| :--- | :--- |
| 借款前看协议 | 已知息费、逾期节点模拟、尚未量化的收费 |
| 已经逾期 | 按日期重建已知账目，拆分本金、利息及各项费用 |
| 多家机构介入 | 区分平台、出借人、担保方、代偿方、受让方和催收方 |
| 平台金额对不上 | 在同一日期比较余额，列出未解释的差额 |
| 材料存在冲突 | 保留来源和差异，说明哪一项影响结果 |

目前按单笔人民币借款计算。已有明确分期表时，支持等额本息、等额本金、先息后本和不规则分期的逐期记账。借款前快捷模拟目前仅支持等额本息。

**仍需人工核对：** 扫描件识别、合同关联、复杂复利、提前还款、退款冲正、重组后的计费变化，以及部分代偿或转让的金额分配。材料无法支持精确计算时，会说明限制。输出用于核对账目，不决定合同效力或应否偿还。

## 准确性怎样保证

- 每个重要金额和规则保留出处，公开模板与实际签署材料分开处理。
- 逐笔流水的真实性与整段还款记录的完整性分别检查。
- 总体计算可信度受最弱的关键证据限制；权重代表证据优先级，不代表准确率。
- 金额用确定性脚本计算，未知收费单独列出。
- 当前到期、未到期计划和剩余总额分别展示，债权事件按生效日期处理。

## 隐私

计算脚本在本机运行，不主动发起网络请求。Codex 读取材料时的数据处理取决于你使用的模型与运行环境；这不等于整条流程离线。请勿把个人协议、流水或身份信息上传到公开仓库、Issue 或评论区。

## 中英文术语

本工具面向中国消费借贷。下列英文用于解释中文概念，不构成官方译名，也不表示其他司法辖区适用相同规则。具体规则仍需按贷款主体、合同日期和适用范围核对。

| 中文 | English |
| :--- | :--- |
| 综合融资成本 | All-in financing cost |
| 逾期罚息 | Overdue penalty interest |
| 融资担保 / 反担保 | Financing guarantee / counter-guarantee |
| 代偿 / 追偿 | Payment by a guarantor / recovery from the borrower |
| 债权转让 / 受让方 | Assignment of a claim / assignee |
| 提前到期 | Acceleration of repayment obligations |
| 权益包 | Bundled benefits or membership package |
| 贷款市场报价利率（LPR） | Loan Prime Rate (LPR) |
| 民间借贷 | Private lending in the Chinese legal context |
| 司法保护上限 | Upper limit of judicial protection |
| 个人贷款综合融资成本明示表 | Personal loan all-in financing cost disclosure statement |
| 《个人贷款业务明示综合融资成本规定》 | Provisions on Disclosure of All-in Financing Costs for Personal Loan Business |
| 国家金融监督管理总局 / 中国人民银行 | National Financial Regulatory Administration (NFRA) / People's Bank of China (PBOC) |

风险提示和来源见 [Risk Warnings](references/risk-warnings.md)。

<details>
<summary>技术说明：命令、目录与测试</summary>

计算脚本需要 Python 3.10 或更新版本，不依赖第三方包。完成条款提取和字段核对后运行：

```bash
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format markdown
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format markdown --detail full
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format json --output result.json
```

借款前等额本息模拟使用 `scripts/calculate_debt.py`。结构定义见 [输入说明](references/input-schema.md) 和 [JSON Schema](schemas/overdue-case.schema.json)。

```text
debt-cost-checker/
├── SKILL.md           任务入口与处理原则
├── agents/            Codex 界面信息
├── scripts/           金额计算与结构化脱敏工具
├── references/        证据分级、债权关系、风险提示
├── schemas/           结构化字段定义
└── tests/             计算与边界情况测试
```

```bash
python3 -m unittest discover -s tests -v
```

当前为 Alpha 版本。37 项自动测试覆盖计算及关键边界；完整真实协议链路的端到端验证仍待完成。测试中的数据均为人工构造，不含借款人的输入材料。

</details>
