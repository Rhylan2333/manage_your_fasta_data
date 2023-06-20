# manage_your_fasta_data
大数据辅修毕业设计源码。《一个基于HBase的用于管理FASTA格式生物信息数据的B/S架构应用的设计与实现》

- 测试环境使用单机模式的 HBase，请看`main.py`中的注释。
```
uvicorn main:app --reload
```
```
nohup python -u "main.py" >> main.log 2>&1 &!
```
都可以启动应用。
