---
name: generate-task-summary
description: Triggered when the user says "SUMMARY". Generates a structured Chinese summary markdown file in the docs folder documenting requirements, discussions, and code changes since the last summary.
---

# Task Summary Workflow

When the user says `SUMMARY`, execute the following steps:

1. **Determine Build Version**: Get the current time in GMT+8 and format `BUILD_VERSION` as `%Y%m%d-%H%M`.
2. **Review Context**: Gather all requirements, key discussions, and code modifications made since the last `SUMMARY`.
3. **Create File**: Create a new Markdown file in the `docs/` directory named:
   `{BUILD_VERSION} - done - {task brief title}.md`
   *(Ensure `{task brief title}` is concise and descriptive).*
4. **Write Content (in Chinese)**: Use the following template:

   # {BUILD_VERSION} {任务简短标题} 

   ## 1. 需求与目标
   - ...

   ## 2. 关键讨论与决策
   - ...

   ## 3. 代码变更记录
   - `文件路径`: 变更说明...

   ---
   *签名: {Agent Name} ({AI Model Name})*

