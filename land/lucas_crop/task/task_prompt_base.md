# 欧洲 LUCAS 2012–2018 作物序列类型点产品构建（Base）

## Objective

仅使用提供的 Harmonised LUCAS 公开观测，重建覆盖 2012、2015 和 2018 三次调查的欧洲稀疏点作物序列类型产品。你需要自己设计并论证一个确定性八类分类方法；不要照抄某个未提供的作者流程。

使用上述八个频率字段构建 8 类语义类型。**Base 限制：不得使用“先 PCA 保留 7 个成分、再使用 Ward 型层次聚类”的作者流程。**你必须选择并论证另一个确定性、可复现的多变量分类方法（例如划分聚类、原型方法、无 PCA 的层次聚类、基于规则的科学等价方法或其组合）。固定随机种子并记录软件版本。

最终八个语义标签必须一一对应八个簇：

```text
cereals
rapeseed and cereals
sunflower and cereals
pulses and cereals
root crops and cereals
forage legumes and cereals
temporary grasslands
corn and cereals
```

语义标签不能随意命名。每个标签在簇中心上必须与其同名特征有最大主导性：`cereals` 簇的 `cereals` 中心应高于其他七个特征；七个非纯谷物标签也必须满足同名非谷物特征高于该簇的其他非谷物特征。若采用全局一对一匹配，必须解释并列消歧规则。

## Input

唯一输入是 `input/lucas_harmo_uf.zip`，SHA-256 为 `e7d2823105bd35a8e9d3d67e830f332f60f3eee304f8ff13b680cb7f96326cc1`。ZIP 内含 `lucas_harmo_uf.csv`：UTF-8 逗号分隔表，约 1.60 GB、1,351,293 行、117 列。关键源字段为 `point_id,year,nuts0,nuts2,nuts3,th_lat,th_long,lc1`。建议流式读取并尽早过滤。

## Product construction

1. 只使用 `year` 为 2012、2015、2018 的记录。
2. 保留 `lc1` 属于以下集合的记录：

```text
B11 B12 B13 B14 B15 B16 B17 B18 B19
B21 B22 B23
B31 B32 B33 B34 B35 B36 B37
B41 B42 B43 B44 B45
B51 B52 B53 B54 B55 E20
```

3. 以 `(point_id,nuts0,nuts2,th_lat,th_long)` 为三期透视身份。身份字段必须非空，每年必须恰有一条无冲突记录，并且三年都满足上述农业代码条件。
4. 只删除三年 `lc1` 全部为 `E20` 的序列；含部分 `E20` 的混合序列必须保留，并将这些 `E20` 计入临时草地。
5. `nuts3` 使用该点三期记录中唯一的非空值；不得用外部行政区数据补充。
6. 最终必须得到恰好 21,620 个唯一 `point_id`。

### Eight frequency fields

每个频率都是三期中相应代码出现次数除以 3，允许值只有 `0`、`1/3`、`2/3`、`1`。分组固定为：

|输出字段|源代码|
|---|---|
|`cereals`|B11、B12、B13、B14、B15、B18、B19|
|`corn`|B16|
|`rapeseed`|B32|
|`sunflower`|B31|
|`pulses`|B33、B41|
|`root_crops`|B21、B22、B23|
|`forage_legumes`|B51、B52|
|`temporary_grasslands`|B53、B55、E20|

`B17` 参与支持筛选但不计入八个频率字段。B34–B37、B42–B45、B54 等已接受代码也不计入八个频率字段。因此八个频率之和可以小于 1，严禁重新归一化。

## Prohibited data

不得联网、搜索论文、使用作者代码或产品、外部农业数据、独立验证资料、隐藏 evaluator 或宿主机其他目录。不得读取 `reference/`、`expert_product/`、私有 evaluator、旧运行结果或任何外部数据。

## Output

生成 `output/crop_sequence_product.csv`，UTF-8 编码，按 `point_id` 数值升序，列顺序严格为：

```text
point_id,nuts0,nuts2,nuts3,latitude,longitude,lc1_2012,lc1_2015,lc1_2018,cereals,corn,rapeseed,sunflower,pulses,root_crops,forage_legumes,temporary_grasslands,crop_sequence_type
```

- 恰好 21,620 行，`point_id` 唯一；
- `latitude/longitude` 分别来自 `th_lat/th_long`，不得插值、格网化或不必要地舍入；
- `lc1_2012/lc1_2015/lc1_2018` 保存公开输入中的原始 `lc1` 代码；
- 八个频率必须有限且属于允许的三分数集合；
- `crop_sequence_type` 必须属于上述八个语义标签。

### Other deliverables

所有交付写入 `output/`：

- `output/process_lucas.py`：从唯一 ZIP 输入完整重建产品与图件的代码；
- `output/report.md`：说明输入检查、支持筛选计数、频率构造、分类方法、语义命名、每类点数、软件版本、质量检查和局限；
- `output/crop_sequence_map.png`：单幅图绘制全部点，按八个语义类型着色，含清晰英文图例和坐标标签；
- CSV 必须按 `point_id` 数值升序。

## Evaluation

Evaluation checks deliverable completeness, schema and physical consistency, followed by private expert-reference and independent-observation quality gates. Numerical thresholds and private supports are not disclosed.
