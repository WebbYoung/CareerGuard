"""单进程本机服务入口：python run.py。"""
import asyncio
import os
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware
from .config import ROOT, CORS_ORIGINS
from .api import router
from .store import store
from .platform_api import router as platform_router, load_model_settings
from .database import ensure_superuser
from .vision_api import router as vision_router
from .onboarding_api import router as onboarding_router
from .model_api import router as model_router
from .resume_api import router as resume_router
from .company_api import router as company_router
from .services import model_gateway
from .assistant_api import router as assistant_router
from .account_api import router as account_router
from .recruitment_api import router as recruitment_router
from .mail_api import router as mail_router
from .services import vision


@asynccontextmanager
async def lifespan(app):
    ensure_superuser()
    load_model_settings()
    model_gateway.load_settings()
    async def sweeper():
        while True:
            await asyncio.sleep(60)
            store.reap()
            vision.monitors.reap()
    task = asyncio.create_task(sweeper())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    with store.lock:
        store.sessions.clear()
    with vision.monitors.lock:vision.monitors.items.clear()
    vision.close_models()


app = FastAPI(title='求职安全体检平台', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
# 默认只信任本机 Host；部署到反向代理后由 EXTRA_ALLOWED_HOSTS 追加对外域名/IP，逗号分隔。
_ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver'] + [
    h.strip() for h in os.getenv('EXTRA_ALLOWED_HOSTS', '').split(',') if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)


@app.middleware('http')
async def security_headers(request: Request, call_next):
    origin = request.headers.get('origin')
    origin_norm = origin.rstrip('/') if origin else ''
    # 白名单跨域来源（EXTRA_CORS_ORIGINS）不算跨站，交给 CORSMiddleware 处理。
    cors_origin = bool(origin_norm) and origin_norm in CORS_ORIGINS
    home_navigation = (request.method == 'GET' and request.url.path == '/' and
                       request.headers.get('sec-fetch-mode') == 'navigate' and
                       request.headers.get('sec-fetch-dest') == 'document')
    if origin and origin_norm != str(request.base_url).rstrip('/') and not cors_origin:
        response = JSONResponse({'detail':'拒绝跨站请求。'}, status_code=403)
    elif request.headers.get('sec-fetch-site') == 'cross-site' and not home_navigation and not cors_origin:
        response = JSONResponse({'detail':'拒绝跨站请求。'}, status_code=403)
    else:
        protected=('/api/materials','/api/risk','/api/privacy','/api/career','/api/audit','/api/session/data','/api/jobs')
        if any(request.url.path==p or request.url.path.startswith(p+'/') for p in protected):
            from .platform_api import current
            from fastapi import HTTPException
            try:
                current(request)
            except HTTPException as exc:
                response=JSONResponse({'detail':exc.detail},status_code=exc.status_code)
            else:
                response=await call_next(request)
        else:
            response = await call_next(request)
    response.headers.update({
        'Cache-Control':'no-store', 'Pragma':'no-cache', 'X-Content-Type-Options':'nosniff',
        'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY',
        'Permissions-Policy':'camera=(self), microphone=(self), geolocation=()',
        'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src "+' '.join(["'self'", *CORS_ORIGINS])+"; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    })
    return response


# 必须在 security_headers 之后注册：add_middleware 后加的在外层，
# 这样 CORS 预检在进入上面那道跨站判定之前就被处理掉。
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
        allow_headers=['Accept', 'Content-Type', 'X-CSRF-Token', 'X-Requested-With', 'Authorization'],
        expose_headers=['X-CSRF-Token'],
        max_age=600,
    )


@app.exception_handler(Exception)
async def generic_error(request, exc):
    # 不将包含原始材料或文件解析详情的异常返回前端。
    return JSONResponse({'detail':'处理未完成，请检查材料格式或稍后重试。'}, status_code=500,
                        headers={'Cache-Control':'no-store'})


app.include_router(router)
app.include_router(platform_router)
app.include_router(vision_router)
app.include_router(onboarding_router)
app.include_router(model_router)
app.include_router(resume_router)
app.include_router(company_router)
app.include_router(assistant_router)
app.include_router(account_router)
app.include_router(recruitment_router)
app.include_router(mail_router)
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')


@app.get('/')
async def index():
    return FileResponse(ROOT/'static'/'index.html')


@app.get('/company/register')
async def company_register_page():
    return FileResponse(ROOT/'static'/'company-register.html')


@app.get('/company')
@app.get('/company/overview')
@app.get('/company/jobs')
@app.get('/company/publish')
@app.get('/company/candidates')
@app.get('/company/mail')
async def company_console_page(request:Request):
    from .platform_api import identity
    from fastapi import HTTPException
    try:user=identity(request)
    except HTTPException:return RedirectResponse('/login?next=company',status_code=303)
    if user['role']!='company':return JSONResponse({'detail':'请使用企业账号进入企业工作台。'},status_code=403)
    return FileResponse(ROOT/'static'/'company-console.html')


@app.get('/app')
async def workbench(request:Request):
    from .platform_api import identity
    from fastapi import HTTPException
    try: identity(request)
    except HTTPException: return RedirectResponse('/login',status_code=303)
    return FileResponse(ROOT/'static'/'workbench.html')


@app.get('/admin')
async def administration(request:Request):
    from .platform_api import identity
    from fastapi import HTTPException
    try: identity(request,True)
    except HTTPException as exc:
        if exc.status_code==401: return RedirectResponse('/login?next=admin',status_code=303)
        return JSONResponse({'detail':'仅管理员可访问管理后台。'},status_code=403)
    return FileResponse(ROOT/'static'/'admin.html')


@app.get('/login')
async def login_page():
    return FileResponse(ROOT/'static'/'login.html')


@app.get('/register')
async def register_page():
    return FileResponse(ROOT/'static'/'register.html')


@app.get('/demo')
async def demo_page(request:Request):
    from .platform_api import identity
    from fastapi import HTTPException
    try:identity(request)
    except HTTPException:return FileResponse(ROOT/'static'/'demo.html')
    return RedirectResponse('/app',status_code=303)
