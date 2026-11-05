"""默认只绑定回环地址；不得使用多 worker，因为会话存储位于内存。"""
if __name__ == '__main__':
    import os
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=int(os.getenv('APP_PORT','5088')), workers=1, access_log=False)
