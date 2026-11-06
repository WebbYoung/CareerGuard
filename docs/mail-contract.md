# 站内邮件与可选SMTP契约

挂载：database.SCHEMA追加app.services.mail_schema.SCHEMA（纯DDL），主应用include app.mail_api.router。依赖recruitment_schema.job_applications(id,user_id,job_id,company_id,share_resume,status)；公司关联既有job_company_links/company_memberships。

前端加载 `/static/mail-ui.css` 与 `/static/mail-ui.js`，调用 `await CareerMail.init(container)`。兼容别名 `MailUI`。企业候选卡调用 `CareerMail.compose({application_id,subject?,body?})`，先初始化邮件容器；收件人由服务器从投递记录推导。管理员可 `compose({recipient_id})`，仅数值站内用户ID。`MailAdminUI.init(container)`展示可选SMTP管理。组件不覆盖window.api；不调用AI，不解析正文HTML。

接口均位于/api；使用现有cg_auth/cg_session与X-CSRF-Token。GET /mail/inbox、/sent、/threads/{id}、/events?after=N&timeout=0..20只读取邮件。POST /mail/threads/{id}/read才标记当前收件用户已读。POST /mail/threads（company:application_id；admin:recipient_id）与/{id}/reply支持sync_email布尔。每用户每分钟最多20次邮件写操作；验证码申请计入且限5次。

企业新建和续联必须来自本企业的active且share_resume=1投递；校验application.company_id等于岗位关联公司、成员身份及公司approved。普通用户不能发起新会话，只可回复自己的已有会话。另一公司的用户、其他普通用户和无关管理员均不能读取会话。正文Fernet加密，主题纯文本限160字且拒控制字符。列表最多100会话，详情最多500条。内部送达独立于SMTP结果，delivery=internal/email_sent/email_failed/email_unavailable。GET不会隐式标记邮件已读。

SMTP默认关闭。GET/POST /admin/mail/config仅管理员，支持465 TLS或587 STARTTLS，密码及整份配置加密保存，GET不回显密码，保存不连接探测。允许常见官方服务主机与服务器环境变量SMTP_ALLOWED_HOSTS（逗号分隔）中的主机。每次发送解析DNS，拒绝任意非公有地址，将连接绑定到已校验IP；TLS SNI与证书校验仍使用配置域名，STARTTLS不可降级。没有任意目的URL或重定向。

用户先POST /mail/address {email,consent}主动关联（变更邮箱清除验证）；POST /mail/address/send-code由用户触发真实验证码邮件。只有管理员启用SMTP时可用，验证码10分钟/5次尝试/单次消费，响应不含验证码。POST /mail/address/verify {code}完成验证。职业邮件外发必须同时满足收件邮箱verified、consent、手动sync_email和SMTP启用；不接受企业指定外部地址。邮件内容由用户手动提交，模型不会发邮件。SMTP失败不撤销站内信，也不把失败显示为真实外发成功。

离线验证：`.venv/Scripts/python.exe -m pytest tests/test_mail.py -q`。所有SMTP测试使用替身；禁止真实邮件与模型探测。
