# StarrailTextSearch

一个用于星穹铁道游戏文本搜索的Web应用程序，提供快速、准确的文本查询功能。

## 功能特性

- 🔍 **全文搜索**：支持游戏内文本的快速搜索
- 🌐 **Web界面**：现代化的Vue.js前端界面
- 🐍 **Python后端**：高效的Flask服务器
- 📊 **数据管理**：内置数据库构建和维护工具
- 🎨 **美观界面**：响应式设计，支持多种视图模式
- 🔄 **实时更新**：支持数据版本管理和历史回填

## 技术栈

### 前端
- Vue.js 3
- Vite
- JavaScript/ES6+

### 后端
- Python 3.x
- Flask
- SQLite/PostgreSQL

## 安装说明

### 环境要求
- Python 3.8+
- Node.js 16+
- npm 或 yarn

### 后端安装
1. 进入server目录：
   ```bash
   cd server
   ```

2. 创建虚拟环境：
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

### 前端安装
1. 进入webui目录：
   ```bash
   cd webui
   ```

2. 安装依赖：
   ```bash
   npm install
   # 或
   yarn install
   ```

## 使用方法

### 启动后端服务器
```bash
cd server
python server.py
```

### 启动前端开发服务器
```bash
cd webui
npm run dev
# 或
yarn dev
```

### 构建前端生产版本
```bash
cd webui
npm run build
```

### 数据构建
```bash
cd server/dbBuild
python DBBuild.py
```

## 项目结构

```
StarrailTextSearch/
├── server/                 # Python后端
│   ├── data_paths.py      # 数据路径配置
│   ├── server.py          # Flask服务器主文件
│   ├── textmap_service.py # 文本映射服务
│   ├── requirements.txt   # Python依赖
│   └── dbBuild/           # 数据库构建工具
│       ├── builder.py
│       ├── DBBuild.py
│       ├── DBInit.py
│       └── history_backfill.py
├── webui/                 # Vue.js前端
│   ├── public/            # 静态资源
│   ├── src/
│   │   ├── components/    # Vue组件
│   │   ├── pages/         # 页面组件
│   │   ├── router/        # 路由配置
│   │   ├── stores/        # 状态管理
│   │   ├── utils/         # 工具函数
│   │   └── views/         # 视图组件
│   ├── package.json       # Node.js配置
│   └── vite.config.js     # Vite配置
├── static/                # 静态文件
├── templates/             # HTML模板
├── .gitignore            # Git忽略文件
└── README.md             # 项目说明
```

## 主要组件

### 后端服务
- **server.py**: 主服务器文件，处理API请求
- **textmap_service.py**: 文本映射和搜索逻辑
- **dbBuild/**: 数据库初始化和数据导入工具

### 前端组件
- **SearchBar.vue**: 搜索输入组件
- **ResultCard.vue**: 搜索结果展示
- **DetailView.vue**: 详细内容查看
- **SearchView.vue**: 主搜索页面

## API接口

### 搜索接口
```
GET /api/search?q={query}&page={page}&limit={limit}
```

### 详情接口
```
GET /api/detail/{type}/{id}
```

### 数据状态
```
GET /api/status
```

## 开发指南

### 代码规范
- 使用ESLint进行JavaScript代码检查
- 使用Black进行Python代码格式化
- 遵循Vue.js官方风格指南

### 提交规范
- 使用清晰的提交信息
- 功能分支开发，合并到main分支

## 贡献

欢迎提交Issue和Pull Request！

1. Fork本项目
2. 创建功能分支：`git checkout -b feature/AmazingFeature`
3. 提交更改：`git commit -m 'Add some AmazingFeature'`
4. 推送分支：`git push origin feature/AmazingFeature`
5. 提交Pull Request

## 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。