# GitHub Issues

需求、规格和缺陷记录在 [hqy2435662352/branchxml](https://github.com/hqy2435662352/branchxml/issues)。使用 GitHub CLI。首次写入前用 `gh repo view --json nameWithOwner` 核对目标，特别是从 fork 工作时。

- 创建议题用 `gh issue create --title "…" --body-file <file>`。多行正文保存在文件中。
- 查看议题用 `gh issue view <number> --comments`，查看待办用 `gh issue list --state open`。按需用 `--label` 过滤。
- 更新标签用 `gh issue edit <number> --add-label <label>` 或 `--remove-label`。含义见 [triage-labels.md](triage-labels.md)。
- 子任务用 GitHub sub-issues 关联。阻塞关系用 GitHub issue dependencies 表示。对应功能不可用时，在子任务正文写明 `Part of #<parent>` 或 `Blocked by: #<blocker>`。
- 补充信息用 `gh issue comment <number> --body-file <file>`。关闭前记录处理结果，然后执行 `gh issue close <number>`。

PRs as a request surface: no.
