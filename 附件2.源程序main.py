from typing import Union, List

from fastapi import FastAPI, Request, Form, Response, File, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.responses import RedirectResponse

import happybase
import hashlib

import time
import os
import re

class Item(BaseModel):
    name: str
    description: Union[str, None] = None
    price: float
    tax: Union[float, None] = None


app = FastAPI()
# 使用 “nohup python -u "main.py" >> main.log 2>&1 &!” 启动此程序

# 挂载模版文件夹
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def read_root():
    return {"Hello World": "Welcome to Caicai's Website."}


# @app.get("/hello/{id}", response_class=HTMLResponse)
# async def hello(request: Request, id: str):
#     return templates.TemplateResponse(
#         name="hello.html",
#         context={
#             "request": request,
#             "id": id
#             }
#         )


@app.get("/hello/")
async def hello(request: Request):
    return templates.TemplateResponse(name="hello.html", context={
        "request": request,
        })


@app.get("/index/")
async def index(request: Request):
    return templates.TemplateResponse(name="index.html", context={
        "request": request,
        })


@app.get("/managebioseq/")
async def managebioseq(request: Request):
    # [使用biopython处理序列数据](https://cloud.tencent.com/developer/article/1771285)
    return templates.TemplateResponse(name="managebioseq.html", context={
        "request": request,
        })


@app.get("/managebioseq/login/", response_class=HTMLResponse)
async def managebioseq_login(request: Request):
    # 不论是否登录都先
    return templates.TemplateResponse(name="managebioseq_login.html", context={'request': request})


# 进行登录验证保护
# 添加USER_INFO数据模型类，用于描述用户信息:
class USER_INFO():
    def __init__(self, user_ID, pwd):
        self.user_ID = user_ID
        self.pwd = pwd


@app.post("/managebioseq/logged/")
async def managebioseq_logged(request: Request, username: str = Form(...), password: str = Form(...)):
    # 实例化USER_INFO，查询用户信息
    user_info = USER_INFO(username, hashlib.sha256(password.encode('utf-8')).hexdigest())
    # 连接hbase数据库
    connection = happybase.Connection('localhost', port=9090)
    table_uname_pwd = connection.table('user_info')
    # 查询用户名和密码
    row_check = table_uname_pwd.row(username)
    if row_check:
        # 如果密码匹配，登录成功
        if row_check[b'info:pwd'].decode() == user_info.pwd:
            response = Response(status_code=303)
            response.headers["Location"] = "http://caicaiweb.top:8000/managebioseq/logged/"
            return response
        # 密码错误
        else:
            error_msg = "密码错误"
            return templates.TemplateResponse("managebioseq_login.html", {'request': request, 'error': error_msg, 'alert': "showAlert('" + error_msg + "');"})
    # 用户名不存在
    else:
        error_msg = "用户名不存在"
        return templates.TemplateResponse("managebioseq_login.html", {'request': request, 'error': error_msg, 'alert': "showAlert('" + error_msg + "');"})


class FASTA_SEQUENCE():
    def __init__(self, seq_id, seq_seq, renamed_id=None, seq_description=None, seq_type=None, subtab_id=None):
        self.seq_id = seq_id
        self.seq_seq = seq_seq
        self.renamed_id = renamed_id
        self.seq_description = seq_description
        self.seq_type = seq_type
        self.subtab_id = subtab_id

class FASTA_HBASE_SUBTABLE():
    def __init__(self, subtab_id):
        self.subtab_id = subtab_id

# 上传FASTA文件功能的实现
# 定义上传FASTA文件的接口
@app.post("/managebioseq/logged/upload_fasta")
async def upload_fasta(request: Request, username: str, file: UploadFile = File(...)):
    if len(file.file) > 200*1024*1024 or file.content_type != "str":
        context = {"request": request, "error_msg": "上传失败！请检查文件大小以及格式后重新上传。"}
        return templates.TemplateResponse("managebioseq_upload_fasta.html", context)
    records = SeqIO.parse(file.file, "fasta")
    for record in records:
        seq_id = record.id
        seq_description = record.description
        seq_seq = str(record.seq)
        connection = happybase.Connection('localhost', port=9090)
        table = connection.table(username)
        row_id = str(time.time())
        table.put(row_id, {'Seq_Show:seq_ID': seq_id,
                            'Seq_Show:seq_Seq': seq_seq,
                            'Seq_Info:seq_Description': seq_description})
    context = {"request": request, "success_msg": "上传成功！您可以关闭此页面。"}
    return templates.TemplateResponse("managebioseq_upload_fasta.html", context)


# FASTA序列查询功能的实现
# 定义FASTA序列查询接口
@app.post("/managebioseq/logged/search_seq")
async def search_seq(request: Request, username: str, search_col: str, keyword: str):
    connection = happybase.Connection('localhost', port=9090)
    table = connection.table(username)
    rows = table.scan(filter=f"SingleColumnValueFilter('{search_col}', =, 'substring:{keyword}')")
    seq_links_html = ""
    for row in rows:
        seq_id = row['seq_ID']
        seq_description = row['seq_Description']
        link = f'<div class="seq-link">\
                    <a href="/managebioseq/logged/managebioseq_seq_detail?{search_col}={keyword}"><strong>{keyword}</strong></a>\
                    <p>seq_ID: {seq_id}</p>\
                    <p>Description: {seq_description}</p>\
                </div>'
        seq_links_html += link
    return templates.TemplateResponse(
        "managebioseq_search_seq_links.html",
        {
            "request": request,
            "username": username,
            "seq_links_html": seq_links_html,
            "keyword": keyword,
            "search_col": search_col
        }
    )


# 定义FASTA序列详情页接口
@app.get("/managebioseq/logged/search_seq_detail")
async def search_seq_detail(request: Request, username: str, row_id: str):
    connection = happybase.Connection('localhost', port=9090)
    table = connection.table(username)
    row = table.row(row_id)
    seq_id = row[b'Seq_Show:seq_ID'].decode()
    seq_seq = row[b'Seq_Show:seq_Seq'].decode()
    seq_description = row[b'Seq_Info:seq_Description'].decode()
    renamed_id = row[b'Seq_Show:renamed_ID'].decode()
    seq_type = row[b'Seq_Info:seq_Type'].decode()
    subtab_id = row[b'Seq_Info:subtab_ID'].decode()
    context = {
        "request": request,
        "seq_id": seq_id,
        "seq_seq": seq_seq,
        "seq_description": seq_description,
        "renamed_id": renamed_id,
        "seq_type": seq_type,
        "subtab_id": subtab_id
    }
    return templates.TemplateResponse("managebioseq_search_seq_detail.html", context)


# FASTA序列修改功能的实现
# 校验用户输入
def check_input(seq_id, seq_seq, renamed_id, seq_description, seq_type, subtab_id):
    # 校验seq_id, seq_seq, renamed_id符合字符串规范
    if not (re.match(r'[a-zA-Z0-9-_]', seq_id) and re.match(r'[a-zA-Z0-9-_]', seq_seq) and re.match(r'[a-zA-Z0-9-_]', renamed_id)):
        return False
    # 校验seq_description符合字符串规范
    if not re.match(r'\w+', seq_description):
        return False
    # 校验seq_type为"protein"或"nucleic_acid"
    if seq_type not in ["protein", "nucleic_acid"]:
        return False
    # 校验subtab_id符合字符串规范
    if not re.match(r'[a-zA-Z0-9-_]', subtab_id):
        return False
    return True


# 定义FASTA序列修改接口
@app.get("/managebioseq/logged/edit_seq")
async def edit_seq(request: Request, username: str, seq_id: str):
    connection = happybase.Connection('localhost', port=9090)
    table = connection.table(username)
    row = table.row(seq_id)
    seq_id = row[b'Seq_Show:seq_ID'].decode()
    seq_seq = row[b'Seq_Show:seq_Seq'].decode()
    seq_description = row[b'Seq_Info:seq_Description'].decode()
    renamed_id = row[b'Seq_Info:Renamed_ID'].decode()
    seq_type = row[b'Seq_Info:Seq_Type'].decode()
    subtab_id = row[b'Seq_Info:SubTab_ID'].decode()
    context = {"request": request, "seq_id": seq_id, "seq_seq": seq_seq,
        "seq_description": seq_description, "renamed_id": renamed_id,
        "seq_type": seq_type, "subtab_id": subtab_id}
    if request.method == "POST":
        form = await request.form()
        new_seq_id = form["seq_id"]
        new_seq_seq = form["seq_seq"]
        new_renamed_id = form["renamed_id"]
        new_seq_description = form["seq_description"]
        new_seq_type = form["seq_type"]
        new_subtab_id = form["subtab_id"]
        # 校验并更新
        if check_input(new_seq_id, new_seq_seq, new_renamed_id, new_seq_description, new_seq_type, new_subtab_id):
            table.put(seq_id, {
                b'Seq_Show:seq_ID': new_seq_id.encode(),
                b'Seq_Show:seq_Seq': new_seq_seq.encode(),
                b'Seq_Show:renamed_ID': new_renamed_id.encode(),
                b'Seq_Info:seq_Description': new_seq_description.encode(),
                b'Seq_Info:Seq_Type': new_seq_type.encode(),
                b'Seq_Info:SubTab_ID': new_subtab_id.encode()
            })
            context["msg"] = "修改成功！您可以关闭此页面"
            return RedirectResponse(request.url)
        else:
            context["msg"] = "输入不符合规范，请重新输入!"
    return templates.TemplateResponse("managebioseq_seq_edit.html", context)


# 定义FASTA序列删除接口
# 定义db_conn对象
class DBConnection:
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username
        self.conn = happybase.Connection(host=self.host, port=self.port)
        self.table = self.conn.table(self.username)
    # 删除行
    def delete_row(self, rowkey):
        self.table.delete(rowkey)
    # 扫描表中所有数据
    def scan(self, family):
        for key, data in self.table.scan(family):
            print(key, data)
    #关闭连接
    def close(self):
        self.conn.close()


# FASTA序列删除
@app.post("/managebioseq/logged/delete_seq")
async def delete_seq(request: Request, username: str, row_id: str = Form(...)):
    db_conn = DBConnection('localhost', 9090, username)
    # 查询FASTA序列行键
    rowkey = db_conn.table.row(row_id)
    # 删除FASTA序列对应的行
    db_conn.delete_row(rowkey)
    # 提示删除成功
    msg = 'FASTA序列删除成功！您可以关闭此页面'
    return templates.TemplateResponse('managebioseq_seq_delete.html',
                                    context={'request': request,
                                            'msg': msg})


# 定义FASTA序列表查询接口
@app.get("/managebioseq/logged/search_seq_subtab")
async def managebioseq_seq_list_view(request: Request, username: str):
    # 检索用户名对应HBase表
    table = DBConnection('localhost', 9090, username).table(username)
    # 若HBase表为空,提示用户
    if not table.rows:
        msg = '您没有录入数据!'
        return templates.TemplateResponse("managebioseq_seq_subtab.html",
                                        context={'request': request, 'msg': msg})
    # 否则获取`Seq_Show:subtab_ID`列所有值
    subtab_ids = [x[1] for x in table.scan(columns=['Seq_Show:subtab_ID'])]
    # 去重后返回FASTA序列表名称
    subtab_ids = list(set(subtab_ids))
    return templates.TemplateResponse("managebioseq_seq_subtab.html",
                                    context={'request': request,
                                            'subtab_ids': subtab_ids,
                                            'username': username})


# FASTA序列表跳转到操作面板
@app.get("/managebioseq/logged/search_seq_subtab_show")
async def managebioseq_seq_detail_view(request: Request, username: str, subtab_id: str):
    # 根据FASTA序列表名称检索FASTA序列
    rows = DBConnection('localhost', 9090, username).table(username).scan(filter=f"Seq_Show:subtab_ID = '{subtab_id}'")
    response = Response(status_code=303)
    response.headers["Location"] = "http://caicaiweb.top:8000/managebioseq/logged/"
    return templates.TemplateResponse("managebioseq_logged.html",
                                    context={'request': request,
                                            'rows': rows,
                                            'subtab_id': subtab_id})


# 定义FASTA序列表修改接口
@app.post("/managebioseq/logged/update_seq_subtab")
async def managebioseq_update_seq_subtab(request: Request, username: str, subtab_id: str, new_subtab_id: str):
    connection = happybase.Connection('localhost')
    table = connection.table(username)
    row = table.row(subtab_id)
    if not re.match(r'^[A-Za-z0-9_-]+$', new_subtab_id):
        msg = '新的FASTA序列表名称不符合要求，请重新输入！'
        return templates.TemplateResponse("managebioseq_logged.html",
                                        context={'request': request, 'row': row, 'subtab_id': subtab_id, 'msg': msg})
    row.update('Seq_Show:subtab_ID', new_subtab_id)
    msg = 'FASTA序列表修改成功！'
    return templates.TemplateResponse("managebioseq_edit_seq_subtab.html",
                                    context={'request': request, 'msg': msg, 'username': username})


# 定义FASTA序列表删除接口
@app.get("/managebioseq/logged/delete_seq_subtab")
async def managebioseq_delete_seq_subtab(request: Request, username: str, subtab_id: str):
    connection = happybase.Connection('localhost')
    table = connection.table(username)
    rows = table.scan(row_prefix=subtab_id)
    return templates.TemplateResponse("managebioseq_delete_seq_subtab.html",
                                    context={'request': request, 'rows': rows, 'subtab_id': subtab_id})


@app.post("/managebioseq/logged/delete_seq_subtab")
async def managebioseq_delete_seq_subtab(request: Request, username: str, subtab_id: str):
    connection = happybase.Connection('localhost')
    table = connection.table(username)
    rows = table.scan(row_prefix=subtab_id)
    for row in rows:
        table.delete(row.row)  # 删除所有匹配子表ID的行
    table.delete('Seq_Show:subtab_ID', subtab_id)  # 删除子表元数据
    msg = 'FASTA序列表删除成功!'
    return templates.TemplateResponse("managebioseq_delete_seq_subtab.html",
                                    context={'request': request, 'msg': msg, 'username': username})


# 子表管理
@app.get("/managebioseq/logged/seq_subtab")
async def managebioseq_seq_subtab(request: Request, username: str):
    connection = happybase.Connection('localhost')
    table = connection.table(username)
    rows = table.scan(columns=['Seq_Show:subtab_ID'])
    return templates.TemplateResponse("managebioseq_delete_seq_subtab.html",
                                    context={'request': request, 'rows': rows, 'username': username})
# ---

# 以下👇是测试文件上传与读取的路由
@app.post("/managebioseq/logged/files/")
async def files(
    request: Request,
    files_name: List[UploadFile] = File(...),
    files_list: List[bytes] = File(...),
    ):
    return templates.TemplateResponse(
        "managebioseq_file_index.html",
        {
            "request": request,
            "file_names": [file.filename for file in files_name],
            "file_sizes": [len(file) for file in files_list],
            })


@app.post("/managebioseq/logged/create_file/")
async def create_file(
    request: Request,
    file: UploadFile =File(...),
    file_b: bytes =File(...),
    notes: str = Form(...),
    ):
    return templates.TemplateResponse(
        "managebioseq_file_index.html",
        {
            "request": request,
            "file_name": file.filename,
            "file_size": len(file_b),
            "notes": notes,
            "file_b_content_type": file.content_type,
            })


@app.get("/managebioseq/logged/managebioseq_post_file/")
async def hello(request: Request):
    return templates.TemplateResponse(name="managebioseq_post_file.html", context={
        "request": request,
        })

# 以下👇是测试内容
@app.get("/items/{item_id}")
async def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


@app.get("/{item_id}/")
async def item_id(request: Request, item_id):
    return templates.TemplateResponse('learnindex.html', {'request':request, "item_id":item_id})


@app.post("/item/")
async def create_item(item: Item):
    item_dict = item.dict()
    if item.tax:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict


if __name__ == '__main__':
    '''因为使用了新的包——uvicorn，所以要用“python -u "main:app"”命令来启动此应用'''
    import uvicorn
    uvicorn.run("main:app", host='0.0.0.0', port=8000,
                log_level="info")  # host='0.0.0.0'

# 使用👉来调试运行：uvicorn main:app --reload  # 官方推荐的，但是用下面的命令更方便。
# 在web应用的路径下用终端执行👉python -u "main:app"

# 然后去右边的网页访问：http://43.143.232.140:8000/，或者：caicaiweb.top:8000/

# [在服务器端后台跑程序（Python）](https://zhuanlan.zhihu.com/p/159551493)
# [FastAPI框架入门 基本使用, 模版渲染, form表单数据交互, 上传文件, 静态文件配置安装](https://www.cnblogs.com/hahaha111122222/p/12781125.html)
