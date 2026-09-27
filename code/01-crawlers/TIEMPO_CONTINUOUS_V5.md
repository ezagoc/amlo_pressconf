# Tiempo 总队列持续采集 v5 — Kevin

这是独立新程序和新运行政策；旧400、808、62、2019的冻结协议保持原样。准备清单不代表已冻结、已联网、文章已验收或整家报纸完成。

## 输入与结果

仅选择原冻结 queue.sqlite 的2018–2025四类：new_urls、old_error_review、old_short_review、old_missing_fields_review。所有原列逐格绑定；不改类、不用目录日期填写文章日期、不按政治栏目筛选。完整排除原四计划2270网址，包括旧2019尚未抓完的输入。原正确结构记录保留不重抓；它们未全部逐篇人工认证。两条old_missing_fields_review保留baseline_protected=1；新补抓独立保存，不替换旧记录。

总准备清单拆成每计划最多2000、每存储批次最多80、每400及末尾统计。每行始终not_reviewed；article_acceptance=false，无人工PASS、无operator approval。源缺标题保留title=null/error，失败和所有部分字段都在all_results；source_unavailable/服务失败/隔离/可用候选分别有清单。core_fields_complete只是原生qa=success，并不代表质量通过。native articles会合并批内canonical别名，计数以全部请求行单独统计，不冒充独立文章。

## v5访问政策

- 403、429、明确反爬挑战、外域跳转/身份冲突、非预期访问状态、TLS等非超时传输错误、保存/哈希/读回异常、低于10GiB或无效时钟：保存可得证据后暂停，下一网址不请求。
- 404、410，以及现有Tiempo错误标题精确识别的软错误页：source_unavailable、qa仍error，保留响应和原字段后继续。新闻正文随便出现404不会被当错误页。这些失效链接单独报告，不计服务故障阈值。
- 超时或500–599：同一网址最多总3次，追加尝试前至少5秒、15秒退避。每次原响应（包括部分正文）各自留存，计入真实transport预算；最终原生结果仍一网址一行，不能把3次尝试算3篇文章。
- 穷尽重试的网址才计服务故障；连续3个，或最近80个终局网址中至少8个，则暂停。404等普通失效网址会打断连续服务故障，但不删历史。
- 实际文章日期与目录日期不同、真实很短正文单列source_judgment_flags，保留全部原flag、隔离与Joaquín清单，不计技术异常阈值。
- 常规源缺项、未认识的DOM联合签名不会单独暂停；保留待Joaquín审核。真实未解释正文/日期/结构差异隔离，两行连续同类或滚动80至少3个未解释异常时暂停。单行多flag只算一行。新类型不会自动进入已审registry。
- 技术暂停不能靠跳到下一个子计划绕过；没有自动清除halt文件或重新假批准的功能。

## 保存与恢复

单一总调度锁，加子计划锁；每次请求前持久预留预算和时钟。所有transport响应再写独立快照/元数据，最后原生pilot保存/提交。正常结束或提交前完整终局响应可零重复恢复；完整已提交批次逐格重读。网络已开始但响应未安全落盘、半截账、丢文件、未完成的重试链均保留并明确暂停，需要技术核对，不能声称任意崩溃窗口exactly-once。

总调度逐一完成当前子计划才启动下一计划。跨计划继承最后79条风险记录、最后请求结束时间和全局请求预算，不能把窗口/间隔/额度归零。global progress内部actual_transport_reservations只统计完成子计划；返回状态明确列completed_plan、active_plan与total。整个调度完成返回collection_inputs_finished_pending_Joaquin_review，仍非研究文章验收。

初始化先留槽位再创建子计划：若在这两步中断，后续fail closed。保留progress与partial目录，不删除状态来重建；按完整manifest和无请求证据由技术负责人恢复匹配备份，或另立明确残余范围（仍排除所有实际已请求网址）。不支持无人值守自行“修复”半成初始化。终局完成但completion_receipt写入前中断，则重新验证当前子计划、零追加请求并补回执后继续。

所有子计划完成回执绑定当前快照、原生和派生导出、读回证据；每400只输出固定待审抽样、风险清单与统计，不等待主观人工判断才继续。跨计划source/canonical重复目前仍需最终合并审核；输入requested/url_key集合由原队列和总partition确保不重复，不宣称全球文章去重。

重试证据与原生最终HTML各保留一份，磁盘占用可能高于之前仅原HTML的7.14GiB估计；每请求10GiB底线强制执行，不自动压缩/删除。

## 安装与运行边界

候选在W开发，生产前由root装入GitHub仓库：两个模块到code/01-crawlers/crawler_core，CLI入口到scripts；对应测试保留。运行依赖全部通过实际program_sha256绑定（七个爬虫模块、v4复用模块、独立sourcechecker、v5 worker和scheduler）；registry必须用最终parser/source和当前真正已审例子重建。旧registry不得直接使用。

先独立审查/离线测试，之后root授权首次最多80，再400检查点，才扩大有限执行。不可用默认run-all；总max-fetch-calls、max-plans、max-batches-per-plan均明确指定。

安装后CLI（变量均由root从真实文件填入；下列不是已执行记录）：

```sh
.venv/bin/python code/01-crawlers/scripts/run_tiempo_scheduler_v5.py prepare --queue-db "$QUEUE" --queue-sha256 "$QUEUE_SHA" --exclusions "$EXCLUSIONS" --out "$PREPARED" --start 2018-01-01 --end-exclusive 2026-01-01
.venv/bin/python code/01-crawlers/scripts/run_tiempo_scheduler_v5.py bind --prepared "$PREPARED" --run-dir "$CAMPAIGN" --media-root "$MEDIA" --registry "$REGISTRY" --registry-sha256 "$REGISTRY_SHA" --max-fetch-calls 391593
# root实际授权后，先80；下一次max-batches-per-plan=4可到首400。
.venv/bin/python code/01-crawlers/scripts/run_tiempo_scheduler_v5.py run --run-dir "$CAMPAIGN" --media-root "$MEDIA" --max-plans 1 --max-batches-per-plan 1 --allow-network
```

新campaign只允许Media/data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5_campaigns/<name>；子计划独立在tiempo_continuous_v5/<campaign>__plan_NNNNNN。最后仍须合并新旧证据、去重/覆盖与Joaquín待审清单，不能因有限队列耗尽就称整报完整。
