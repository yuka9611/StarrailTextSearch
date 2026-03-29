# StarrailTextSearch

一个参考 `GenshinTextSearch` 重做的星铁文本搜索首版。

## 功能

- 关键词搜索 `turnbasedgamedata/TextMap` 中的文本
- 支持多语言切换
- 设置页保存默认搜索语言
- 不包含语音播放能力

## 目录

- `server/`: 纯 Python 标准库后端，提供 API 并托管前端构建产物
- `webui/`: Vue 3 + Vite 前端

## 数据目录

默认读取项目同级目录下的 `../turnbasedgamedata`。

## 启动方式

### 1. 启动后端

```bash
cd /Users/yuka9/Downloads/StarrailTextSearch
python3 server/server.py
```

后端默认运行在 `http://127.0.0.1:5000/`。

### 2. 前端开发

```bash
cd /Users/yuka9/Downloads/StarrailTextSearch/webui
npm install
npm run dev
```

Vite 开发服务器会把 `/api` 代理到本地后端。

### 3. 前端构建

```bash
cd /Users/yuka9/Downloads/StarrailTextSearch/webui
npm install
npm run build
```

构建完成后，后端会自动托管 `webui/dist`。
