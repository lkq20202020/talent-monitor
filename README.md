# 人才公寓审核状态云端监控

每 30 分钟检查一次「青山湖人才房屋租赁」系统的申请审核状态，状态变化（尤其是审核通过）时发送邮件通知。

## 工作原理

1. GitHub Actions 定时器每 30 分钟触发一次（`cron: "*/30 * * * *"`）
2. `monitor.py` 调用系统接口 `POST /apg/talentapplicant/pageList` 查询状态
3. 与 `state.json` 中上次的状态比较：
   - **变为「审核通过」** → 发「【重要】复审已通过」邮件，并把 `approved` 置为 true，后续自动跳过
   - **其他变化 / 驳回 / 备注变化** → 发「【提醒】状态有变化」邮件
   - **无变化** → 不发信，仅更新 `state.json`（不产生提交）
4. 状态变化时自动把 `state.json` 提交回仓库，实现跨次运行的状态记忆

## 需要的 Repository Secrets

| Secret | 说明 |
| --- | --- |
| `MOBILE` | 登记手机号 |
| `APPLICANT_ID` | 申请记录 ID（可选，留空则取列表第一条） |
| `MAIL_TO` | 接收通知的邮箱 |
| `SMTP_USER` | 发信邮箱（QQ 邮箱地址） |
| `SMTP_PASS` | QQ 邮箱 SMTP 授权码（16 位，不是登录密码） |

代码中不含任何个人信息，全部通过 Secrets 注入。

## 状态字典

`-1` 审核驳回 · `0` 待审核 · `1` 审核通过 · `2` 撤销审核 · `3` 办理中

## 手动测试

仓库 Actions 页面 → 选择 `talent-apartment-status-check` → Run workflow。

## 注意

- GitHub 定时任务在高峰期可能延迟 5~15 分钟
- 公共仓库连续 60 天无提交会被暂停定时任务；本项目在状态变化时才会提交，长期无事时可手动 Run 一次唤醒
