"""Editable account presentation; uploads are decoded in memory and metadata stripped."""
import io
import warnings
from fastapi import APIRouter,Request,Response,HTTPException
from pydantic import Field
from PIL import Image,ImageOps,UnidentifiedImageError
from .api import Input,payload,read_bytes,compute
from .database import connect,cipher,event
from .platform_api import current,write_guard

router=APIRouter(prefix='/api/account')

class Details(Input):
    nickname:str=Field(default='',max_length=24)
    city:str=Field(default='',max_length=40)
    bio:str=Field(default='',max_length=160)

def presentation(user,row):
    return {'username':user['username'],'role':user['role'],'created':user['created'],
            'nickname':row['nickname'] if row else '', 'city':row['city'] if row else '',
            'bio':row['bio'] if row else '', 'has_avatar':bool(row and row['avatar']),
            'avatar_revision':row['avatar_revision'] if row else 0}

def account(db,user):
    return presentation(user,db.execute('SELECT * FROM account_details WHERE user_id=?',(user['id'],)).fetchone())

@router.get('')
async def get_account(request:Request):
    user=current(request)
    with connect() as db:return account(db,user)

@router.put('')
async def save_account(request:Request):
    user=current(request);data=await payload(request,Details)
    values={k:v.strip() for k,v in data.model_dump().items()}
    for key,value in values.items():
        if any(ord(c)<32 and not (key=='bio' and c in '\n\t') for c in value):raise HTTPException(422,'资料包含无效控制字符。')
    with connect() as db:
        write_guard(db,user)
        db.execute('''INSERT INTO account_details(user_id,nickname,city,bio) VALUES (?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET nickname=excluded.nickname,city=excluded.city,bio=excluded.bio''',
            (user['id'],values['nickname'],values['city'],values['bio']))
        event(db,user['id'],'account_profile_save')
        return account(db,user)

def normalize_avatar(raw,kind):
    formats={'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP'}
    if kind not in formats:raise HTTPException(415,'头像支持PNG、JPEG或WebP静态图片。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format!=formats[kind]:raise HTTPException(415,'图片格式与声明不一致。')
                if source.width*source.height>16000000:raise HTTPException(413,'头像像素不可超过1600万。')
                if getattr(source,'n_frames',1)!=1:raise HTTPException(422,'请使用静态图片作为头像。')
                source.load()
                oriented=ImageOps.exif_transpose(source)
                cropped=ImageOps.fit(oriented.convert('RGBA'),(256,256),method=Image.Resampling.LANCZOS)
                # A fresh image strips EXIF, ICC and arbitrary text chunks from the upload.
                clean=Image.new('RGBA',(256,256));clean.paste(cropped)
                output=io.BytesIO();clean.save(output,format='PNG');return output.getvalue()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'图片无法解码，请选择有效的静态图片。') from None

@router.post('/avatar')
async def upload_avatar(request:Request):
    user=current(request)
    raw=await read_bytes(request,4*1024*1024)
    kind=request.headers.get('content-type','').split(';',1)[0].strip().lower()
    clean=await compute(normalize_avatar,raw,kind)
    with connect() as db:
        write_guard(db,user)
        db.execute('''INSERT INTO account_details(user_id,avatar,avatar_revision) VALUES (?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET avatar=excluded.avatar,avatar_revision=account_details.avatar_revision+1''',
            (user['id'],cipher().encrypt(clean)))
        event(db,user['id'],'account_avatar_update')
        return account(db,user)

@router.get('/avatar')
async def get_avatar(request:Request):
    user=current(request)
    with connect() as db:row=db.execute('SELECT avatar FROM account_details WHERE user_id=?',(user['id'],)).fetchone()
    if not row or not row['avatar']:raise HTTPException(404,'尚未设置头像。')
    try:image=cipher().decrypt(row['avatar'])
    except Exception:raise HTTPException(409,'头像不可读取，请重新上传。') from None
    return Response(image,media_type='image/png',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.delete('/avatar')
async def remove_avatar(request:Request):
    user=current(request)
    with connect() as db:
        write_guard(db,user)
        db.execute('UPDATE account_details SET avatar=NULL,avatar_revision=avatar_revision+1 WHERE user_id=?',(user['id'],))
        event(db,user['id'],'account_avatar_remove')
        return account(db,user)
