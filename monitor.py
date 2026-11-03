# -*- coding: utf-8 -*-
"""
人才公寓复审状态监控 (GitHub Actions 版)
- 查询: POST https://pmsnm.zj-xzh.com/apg/talentapplicant/pageList
- 状态变化 / 审核通过时发送邮件 (QQ 邮箱 SMTP)
- 状态保存在 state.json，由 workflow 提交回仓库，实现跨次运行的记忆
依赖的 Secrets: MOBILE, APPLICANT_ID, MAIL_TO, SMTP_USER, SMTP_PASS
"""
import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from email.header import Header
from email.mime.text import MIMEText

BASE = "https://pmsnm.zj-xzh.com"
STATE_FILE = "state.json"
SITE = "https://pmsnm.zj-xzh.com/applylogin"

MOBILE = os.environ.get("MOBILE", "").strip()
APPLICANT_ID = os.environ.get("APPLICANT_ID", "").strip()
MAIL_TO = os.environ.get("MAIL_TO", "").strip()
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()

STATUS_MAP = {-1: "审核驳回", 0: "待审核", 1: "审核通过", 2: "撤销审核", 3: "办理中"}


def fetch_record():
    body = json.dumps({"mobile": MOBILE, "page": {"page": 1, "size": 10}}).encode()
    req = urllib.request.Request(
        BASE + "/apg/talentapplicant/pageList",
        data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError("接口返回失败: " + json.dumps(data, ensure_ascii=False)[:200])
    items = (data.get("data") or {}).get("content") or []
    if not items:
        raise RuntimeError("未查询到申请记录")
    for it in items:
        if APPLICANT_ID and str(it.get("applicantId")) == APPLICANT_ID:
            return it
    return items[0]


def send_mail(subject, text):
    if not (MAIL_TO and SMTP_USER and SMTP_PASS):
        print("WARN: 邮件参数缺失，跳过发信")
        return False
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = SMTP_USER
    msg["To"] = MAIL_TO
    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, [MAIL_TO], msg.as_string())
    return True


def main():
    if not MOBILE:
        print("ERROR: 缺少 MOBILE secret")
        return 1

    rec = fetch_record()
    status = rec.get("approveStatus")
    label = STATUS_MAP.get(status, "未知(%s)" % status)
    remark = (rec.get("approveRemark") or "").strip()
    reject = (rec.get("rejectComment") or "").strip()
    project = rec.get("projectName") or ""
    resource = rec.get("applyResourceName") or ""
    name = rec.get("fullName") or ""

    old = {}
    if os.path.exists(STATE_FILE):
        try:
            old = json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception:
            old = {}
    old_status = old.get("approve_status")
    old_remark = old.get("remark") or ""
    old_reject = old.get("reject") or ""

    changed = old_status is not None and old_status != status
    remark_changed = old_status == status and (remark != old_remark or reject != old_reject)
    approved = status == 1
    rejected = status == -1

    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    print("时间: %s" % ts)
    print("项目: %s %s %s" % (project, resource, name))
    print("状态: %s (approveStatus=%s)" % (label, status))
    if remark:
        print("备注: %s" % remark)
    if reject:
        print("驳回意见: %s" % reject)
    print("变化: %s" % ("是 %s -> %s" % (STATUS_MAP.get(old_status, old_status), label) if changed else "否"))

    if approved:
        subject = "【重要】人才公寓复审已通过"
        body = ("%s\n\n%s 的「%s %s」申请：%s\n审核状态：%s\n查询时间：%s\n\n"
                "请尽快登录系统查看后续流程（选房/签约）：\n%s\n\n"
                "（本监控检测到通过后将自动停止发信）") % (
            "你的人才公寓申请已通过审核。", name, project, resource,
            "", label, ts, SITE)
        send_mail(subject, body)
    elif rejected or changed or remark_changed:
        subject = "【提醒】人才公寓状态有变化"
        detail = []
        if changed:
            detail.append("状态变化：%s -> %s" % (STATUS_MAP.get(old_status, old_status), label))
        detail.append("当前状态：%s" % label)
        if remark:
            detail.append("审核备注：%s" % remark)
        if reject:
            detail.append("驳回意见：%s" % reject)
        body = "申请：%s %s\n时间：%s\n\n%s\n\n查看详情：%s" % (
            project, resource, ts, "\n".join(detail), SITE)
        send_mail(subject, body)
    else:
        print("无变化，不发信")

    json.dump({
        "approve_status": status,
        "remark": remark,
        "reject": reject,
        "approved": bool(approved),
        "last_check": ts,
    }, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("status=%s\n" % status)
            f.write("changed=%s\n" % ("true" if changed else "false"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("CHECK_ERROR: %s" % e)
        # 出错也尝试通知一次，避免静默失效
        try:
            send_mail("【告警】人才公寓监控异常",
                      "云端监控执行失败：%s\n请检查 https://github.com 上的 Actions 日志。" % e)
        except Exception:
            pass
        sys.exit(1)
