# 启动前请确保依次运行了如下命令
"""
start-hbase.sh  # 在单机模式下，HBase无需依赖Hadoop，可以独立启动运行。
hbase-daemon.sh start thrift  # happybase是基于Thrift 1.0 版本的,所以无法连接Thrift 2服务。它只支持连接Thrift 1 RPC服务。
$ jps  # 应当有如下输出。在HBase单机模式下，RegionServer进程实际上运行在同一JVM进程内，不会作为单独的进程启动。所以，当你执行jps命令查看进程时，只会看到HMaster进程，而不会出现RegionServer进程。这与你的hbase-site.xml配置<hbase.cluster.distributed>false也是一致的。
22354 ThriftServer
17996 HMaster
22542 Jps
"""

# Importing necessary packages
import hashlib
import itertools
from datetime import datetime

# conda install -c conda-forge ……以下所有包，包括 python-multipart
import happybase
from Bio import SeqIO
from fastapi import FastAPI, File, Form, Request, UploadFile
# from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Create an instance of the FastAPI
app = FastAPI()

# Mount the static and template directories
app.mount("/static", StaticFiles(directory="./static/"), name="static")
templates = Jinja2Templates(directory="./templates/")

# @app.get("/")
# async def read_root():
#     return {"Hello World": "Welcome to Caicai's Website."}

# Endpoint for the root URL
@app.get("/")
async def read_item(request: Request):
    # Create a connection to the HBase database
    connection = happybase.Connection('localhost', port=9090)
    table = connection.table('user_info')

    rows = []

    # Scan the table and appending the rows to a list
    for key, data in table.scan():
        rows.append({'row_key': key, 'data': data})
    # Return the template response with the rows
    return templates.TemplateResponse(
        "item_to_test_happybase.html",
        context={
            "request": request,
            "rows": rows
            }
        )


# 进行登录验证保护
# Global variable for current client
current_client = ''  # 一个全局变量，用于“一个用户一章表”

# 添加 UserInfo 数据模型类，用于描述用户信息：
# Class for UserInfo data model
class UserInfo():
    def __init__(self, username, password):
        self.username = username
        self.password = password
    # Method to generate hash using sha256
    def get_hash(self, in_str):
        sha256 = hashlib.sha256()
        sha256.update(in_str.encode('utf-8'))
        return sha256.hexdigest()

# Endpoint for the login page
@app.get("/managebioseq/login/")
async def managebioseq_login(request: Request):
    return templates.TemplateResponse("managebioseq_login.html", context={'request': request})

# Endpoint for the logged in page
@app.post("/managebioseq/logged/")
async def managebioseq_logged(request: Request, username: str = Form(...), password: str = Form(...)):
    # Form(...) 使得 username 和 password 将自动接收表单数据，而不用`username = request.form["username"]`，`password = request.form["password"]`。
    # 但对于复杂的表单，使用`var1 = request.form["var1"]`会更合适。
    # 实例化 User_Info，查询用户信息
    # Create an instance of UserInfo and query the user information
    user_info = UserInfo(username, hashlib.sha256(password.encode('utf-8')).hexdigest())
    # Connect to the HBase database
    connection = happybase.Connection('localhost')
    table_uname_pwd = connection.table('user_info')
    # Query the username and password
    row_check = table_uname_pwd.row(username)
    # If the username exists
    if row_check:
        # If the password matches, login is successful
        if row_check[b'info:pwd'].decode() == user_info.password:
            global current_client
            current_client = username
            return templates.TemplateResponse("managebioseq_logged.html", context={'request': request, 'result': '用户名和密码匹配，登录成功！', 'current_user' : current_client})
        # If the password is incorrect
        else:
            error_msg = "密码错误！请重新输入！！"
            return templates.TemplateResponse("managebioseq_login.html", context={'request': request, 'result': error_msg})
    # If the username does not exist
    else:
        error_msg = "用户名不存在！请重新输入！！"
        return templates.TemplateResponse("managebioseq_login.html", context={'request': request, 'result': error_msg})


# Class for the FastaSequence data model
# 添加 FastaSequence、FastaHBaseSubtable数据模型类，用于描述 FASTA 文件、序列所在子表的信息:
class FastaSequence():
    def __init__(self, seq_id, seq_seq, renamed_id=None, seq_description=None, seq_type=None, subtab_id=None):
        self.seq_id = seq_id
        self.seq_seq = seq_seq
        self.renamed_id = renamed_id
        self.seq_description = seq_description
        self.seq_type = seq_type
        self.subtab_id = subtab_id

# Class for the FastaHBaseSubtable data model
class FastaHBaseSubtable():
    def __init__(self, subtab_id):
        self.subtab_id = subtab_id


# 上传 FASTA 文件功能的实现
# 定义上传 FASTA 文件的接口
@app.get("/managebioseq/logged/upload_fasta/")
async def upload_fasta_file(request: Request):
    # Global variable to store the current client
    global current_client
    return templates.TemplateResponse("managebioseq_upload_fasta_file.html", context={'request': request, 'current_client': current_client})


# 定义上传 FASTA 文件后展示解析结果的接口
@app.post("/managebioseq/logged/upload_fasta_result/")
async def upload_fasta_file_result(request: Request, subtab_id: str = Form(...), file: UploadFile = File(...)):
    # Parse the uploaded FASTA file to get the sequence records
    seq_records = SeqIO.parse(f"{file.filename}", "fasta")
    # Check the parsing result, if seq_records is empty, then the format is incorrect, return an error message
    if seq_records:  # Improvement needed here, enhance validation functionality.
        global current_client
        connection = happybase.Connection('localhost')
        table = connection.table(current_client)
        # Write each sequence record into the HBase table
        for seq_record in seq_records:
            row_id = str(datetime.now()).replace(' ', '_')  # Generate the row key
            seq_id = seq_record.id  # 序列 ID
            seq_description = seq_record.description  # 序列描述
            seq_seq = str(seq_record.seq)  # 序列内容
            table.put(row_id, {'Seq_Show:seq_ID': seq_id,
                                'Seq_Show:seq_Seq': seq_seq,
                                'Seq_Show:renamed_ID': "",  # 序列别名
                                'Seq_Info:seq_Description': seq_description,
                                'Seq_Info:seq_Type': "",  # 序列类型
                                'Seq_Info:subtab_ID': subtab_id,  # 所属子表 ID
                                })
        # Return success message
        return templates.TemplateResponse(
            "managebioseq_upload_fasta_result.html",
            context = {
                'request': request,
                'success_msg': f"上传成功！{current_client} 您可以关闭此页面。",
                'subtab_id': subtab_id,  # Pass the value of subtab_id
                }
            )
    else:
        # Return failure message
        return templates.TemplateResponse(
        "managebioseq_upload_fasta_result.html",
        context = {
            'request': request,
            'error_msg': f"上传失败！{current_client} 请您检查文件大小以及格式后重新上传。您的文件格式是：{file.content_type}",
            'subtab_id': subtab_id,
            }
        )


# 查询 FASTA 序列功能的实现
# 定义查询 FASTA 序列的接口
@app.get("/managebioseq/logged/search_seq/")
async def search_seq(request: Request):
    # 全局变量，存储当前客户端
    global current_client
    return templates.TemplateResponse("managebioseq_search_seq.html", context={'request': request, 'current_client': current_client})

# 定义查询 FASTA 序列查询结果的接口
@app.post("/managebioseq/logged/search_seq_result/")
async def search_seq_result(
    request: Request,
    keyword: str = Form(...),
    search_col: str = Form(...),  # Seq_Show:seq_ID, Seq_Show:seq_Seq, Seq_Show:renamed_ID, Seq_Info:seq_Description, Seq_Info:subtab_ID
    ):
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')  # , port=9090
    table = connection.table(current_client)

    # 使用过滤器扫描指定列的值
    filter_string = f"SingleColumnValueFilter('{search_col.split(':')[0]}', '{search_col.split(':')[-1]}', =, 'substring:{keyword}')"

    rows = table.scan(filter=filter_string)
    rows, rows_copy = itertools.tee(rows)


    if rows:
        # for row in rows:
        #     row_key = row[0]
        #     seq_ID = row[-1][b'Seq_Show:seq_ID']
        #     seq_Seq = row[-1][b'Seq_Show:seq_Seq']
        #     renamed_ID = row[-1][b'Seq_Show:renamed_ID']
        #     seq_Description = row[-1][b'Seq_Info:seq_Description']
        #     seq_Type = row[-1][b'Seq_Info:seq_Type']
        #     subtab_ID = row[-1][b'Seq_Info:subtab_ID']
        row_count = len(list(rows_copy))
        return templates.TemplateResponse(
            "managebioseq_search_seq_links.html",
            {
                "request": request,
                "msg": f'{current_client}，请查阅。',
                "keyword": keyword,
                "search_col": search_col,
                "rows": rows,
                'row_count': row_count
            }
        )
    else:
        return templates.TemplateResponse(
            "managebioseq_search_seq_links.html",
            {
                "request": request,
                "msg": f'出错。{current_client}，请重新查询。',
                "keyword": keyword,
                "search_col": search_col,
                "rows": rows
            }
        )


# 定义查询 FASTA 序列查询结果细节的接口
@app.get("/managebioseq/logged/search_seq_result/{row_key}/")
async def search_seq_result_detail(request: Request, row_key: str):
    # 全局变量，存储当前客户端
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')
    table = connection.table(current_client)
    row_key = row_key
    # 查询特定row_key的行
    row_value = table.row(row_key)
    return templates.TemplateResponse("managebioseq_search_seq_detail.html", context={'request': request, 'current_client': current_client, 'row_key': row_key, 'row_value': row_value})


# 定义删除 FASTA 序列的接口
@app.get("/managebioseq/logged/delete_seq/{row_key}/")
async def delete_seq(request: Request, row_key: str):
    # 全局变量，存储当前客户端
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')
    table = connection.table(current_client)
    row_key = row_key
    # 查询特定row_key的行
    row_value = table.row(row_key)
    # 删除特定row_key的行
    table.delete(row_key)
    error_msg = ""
    success_msg = f"删除了👇<br/>row_key: {row_key}<br/>row_value: {row_value}。"
    return templates.TemplateResponse("managebioseq_delete_seq_result.html", context={'request': request, 'current_client': current_client, 'error_msg': error_msg, 'success_msg': success_msg})


# 定义修改 FASTA 序列的接口
@app.get("/managebioseq/logged/edit_seq/{row_key}/")
async def edit_seq(request: Request, row_key: str):
    # 全局变量，存储当前客户端
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')
    table = connection.table(current_client)
    row_key = row_key
    # 查询特定row_key的行
    row_value = table.row(row_key)
    return templates.TemplateResponse("managebioseq_edit_seq.html", context={'request': request, 'current_client': current_client, 'row_key': row_key, 'row_value': row_value})

@app.post("/managebioseq/logged/edit_seq_result/{row_key}/")
async def edit_seq_result(
    request: Request,
    row_key: str,
    seq_id: str = Form(...),
    seq_seq: str = Form(...),
    renamed_id: str = Form(...),
    seq_description: str = Form(...),
    seq_type: str = Form(...),
    subtab_id: str = Form(...),
    ):
    # 全局变量，存储当前客户端
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')
    table = connection.table(current_client)
    row_key = row_key
    # 修改特定row_key的行
    table.put(row_key, {
        'Seq_Show:seq_ID': seq_id,
        'Seq_Show:seq_Seq': seq_seq,
        'Seq_Show:renamed_ID': renamed_id,  # 序列别名
        'Seq_Info:seq_Description': seq_description,
        'Seq_Info:seq_Type': seq_type,  # 序列类型
        'Seq_Info:subtab_ID': subtab_id,  # 子表ID
        })
    # 查询特定row_key的行
    row_value = table.row(row_key)
    error_msg = ""
    success_msg = f"修改了👇<br/>row_key: {row_key}<br/>新的 row_value: {row_value}"
    # 返回成功信息
    return templates.TemplateResponse("managebioseq_edit_seq_result.html", context={'request': request, 'current_client': current_client, 'error_msg': error_msg, 'success_msg': success_msg, 'row_key': row_key})


# 定义查询 FASTA 序列表的接口
@app.get("/managebioseq/logged/show_subtabs/")
async def show_subtabs(request: Request):
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost', port=9090)
    table = connection.table(current_client)

    dic_subtabs = {}
    for row_key, row_value in table.scan():
        subtab_id  = row_value['Seq_Info:subtab_ID'.encode()].decode()
        if subtab_id not in dic_subtabs:
            dic_subtabs[subtab_id] = 1
        else:
            dic_subtabs[subtab_id] += 1

    return templates.TemplateResponse(
        "managebioseq_show_subtabs.html",
        context={
            'current_client': current_client,
            'request': request,
            'dic_subtabs': dic_subtabs
            })

@app.get("/managebioseq/logged/{subtab_name}/")
async def managebioseq_logged_subtab(request: Request, subtab_name: str):
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')  # , port=9090
    table = connection.table(current_client)
    subtab_name = subtab_name
    # 存儲子表用
    dic_subtabs = {}
    for row_key, row_value in table.scan():
        if row_value['Seq_Info:subtab_ID'.encode()].decode() == subtab_name:
            dic_subtabs[row_key] = row_value
    return templates.TemplateResponse(
        "managebioseq_logged_subtab.html",
        context={
            'request': request,
            'subtab_name': subtab_name,
            'current_user' : current_client,
            'dic_subtabs': dic_subtabs
            }
        )


# 定义删除 FASTA 序列表的接口
@app.get("/managebioseq/logged/delete_subtab/{subtab_name}/")
async def delete_subtab(request: Request, subtab_name: str):
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost', port=9090)
    table = connection.table(current_client)
    subtab_name = subtab_name
    for row_key, row_value in table.scan():
        subtab_id  = row_value['Seq_Info:subtab_ID'.encode()].decode()
        if subtab_name == subtab_id:
            # 删除特定row_key的行
            table.delete(row_key)
    error_msg = ""
    success_msg = f"删除了👇<br/>子表名: {subtab_name}"

    return templates.TemplateResponse(
        "managebioseq_delete_subtab_result.html",
        context={
            'request': request,
            'current_client': current_client,
            'error_msg': error_msg,
            'success_msg': success_msg
            })


# 定义修改 FASTA 序列表的接口
@app.get("/managebioseq/logged/rename_subtab/{subtab_name}/")
async def rename_subtab(request: Request, subtab_name = str):
    return templates.TemplateResponse("managebioseq_rename_subtab.html", context={'request': request, 'subtab_name': subtab_name})

@app.post("/managebioseq/logged/rename_subtab_result/{subtab_name}/")
async def rename_subtab_result(request: Request, subtab_name: str, new_subtab_id : str = Form(...)):
    # 全局变量，存储当前客户端
    global current_client
    # 连接 HBase 数据库
    connection = happybase.Connection('localhost')
    table = connection.table(current_client)
    subtab_name = subtab_name
    for row_key, row_value in table.scan():
        subtab_id  = row_value['Seq_Info:subtab_ID'.encode()].decode()
        if subtab_name == subtab_id:
            # 修改特定row_key的行
            table.put(row_key, {
                'Seq_Info:subtab_ID': new_subtab_id,  # 子表ID
            })
    error_msg = ""
    success_msg = f"修改了👇<br/>旧子表名: {subtab_name}<br/>新子表名: {new_subtab_id}"

    return templates.TemplateResponse(
        "managebioseq_rename_subtab_result.html",
        context={
            'request': request,
            'current_client': current_client,
            'error_msg': error_msg,
            'success_msg': success_msg
            })


# 以下是测试
# 上传文件测试
@app.get("/test_upload_fasta/")
async def test_upload_fasta_file(request: Request):
    return templates.TemplateResponse("test_upload_fasta_file.html", context={'request': request})


@app.post("/test_upload_fasta_result/")
async def test_upload_fasta_file_result(request: Request, subtab_id: str = Form(...), file: UploadFile = File(...)):
    # with open(f"{file.filename}", "wb") as f:
    #     f.write(file.file.read())
    content = ""
    for seq_record in SeqIO.parse(f"{file.filename}", "fasta"):
        content += "<p>" + seq_record.description + "</p>"
        content += "<p>" + str(seq_record.seq) + "</p>"
    return templates.TemplateResponse("test_upload_fasta_result.html", context = {'request': request, 'subtab_id': subtab_id, 'content_type': file.content_type,'content': content})

## 进入工作路径，在终端中运行 $ uvicorn main_开发中:app --reload

if __name__ == '__main__':
    '''因为使用了新的包——uvicorn，所以要用“python -u "main_开发中:app"”命令来启动此应用'''
    import uvicorn
    uvicorn.run("main:app", log_level="info")  # host='0.0.0.0', port=8000,
# 使用👉来调试运行：uvicorn main:app --reload  # 官方推荐的，但是用下面的命令更方便。
# 在web应用的路径下用终端执行👉python3 -u "main_开发中:app"
# nohup python -u "main.py" >> main.log 2>&1 &!