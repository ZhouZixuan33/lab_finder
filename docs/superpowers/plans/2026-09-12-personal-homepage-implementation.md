# 个人主页查找实施步骤

依据已确认的个人主页查找设计，按以下顺序实施：

1. 增加 Tavily Extract provider、两个模型可见工具和结果模型，复用 Tavily Key 与限速器。
2. 实现 HomepageState 及 agent/tools/finalize 三节点图，五次工具尝试后直接整理结果。
3. 将独立图接入新增与单教授更新研究编排，移除原研究图的 lab 选择职责，保留 homepage_url、摘要与论文逻辑。
4. 更新列表、详情和差异页的个人主页展示文字。
5. 使用模拟模型和 HTTP transport 验证循环、消息、Extract 错误与结果校验；运行后端测试、前端测试和构建。

不执行真实教授研究或数据迁移。
