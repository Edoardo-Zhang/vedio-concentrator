# 发布到 GitHub 与后期维护（小白版）

这份文档写给**从没发过 GitHub** 的人。按顺序做，不要跳。

先记住三个名词，后面全靠它们：

| 名词 | 一句话解释 | 在你项目里是什么 |
|---|---|---|
| **仓库（Repository）** | 一个装了项目的文件夹，GitHub 帮你保管 + 记录每一次改动 | `vedio-concentrator` |
| **提交（Commit）** | 一次"存档"，记录你改了哪些文件 | "修了代理探测的 bug" |
| **推送（Push）** | 把本地存档上传到 GitHub | `git push` |

**核心心法：GitHub 上只有两样东西在给人用**

1. **仓库 = 源码**（别人 `git clone` 走的）
2. **Release = 成品 zip**（别人直接下载用的）

你这个项目两个都要：仓库放代码，Release 放 `vedio-concentrator-bundle.zip`。
**只发仓库不发 Release，别人就用不了"下载 zip 双击安装"那条路。**

---

## ⚠️ 动手前先修一个坑

你机器上的 git 提交身份和你的 GitHub 账号**对不上**：

```
现在：user.name  = 2042017558-bot
      user.email = za0833036942@gmail.com
账号：Edoardo-Zhang
```

不改的话，**GitHub 上你的提交不会算在你头上**（头像不显示、贡献图不亮）。先跑这两行：

```powershell
git config --global user.name  "Edoardo-Zhang"
git config --global user.email "你的GitHub注册邮箱"
```

邮箱填你在 GitHub 注册用的那个。不确定就去 GitHub → 右上角头像 → Settings → Emails 看。

---

## 方法一：网页版（最简单，不用装任何东西）

**适合**：只要把代码放上去，不想碰命令行。
**缺点**：一次最多传 100 个文件、单个文件 25 MB 以内，改起来要一个个点。

### 1. 建仓库

1. 打开 https://github.com/new
2. **Repository name** 填 `vedio-concentrator`（必须和你 README 里写的一致，否则链接全错）
3. **Description** 随便填，例如：`给视频链接，自动下载 + 转写 + 生成脑图`
4. 选 **Public**（公开，别人才能下载）。想私密就选 Private
5. **不要**勾 "Add a README file"（我们有自己的 README，勾了会冲突）
6. 点 **Create repository**

### 2. 上传源码

建完会跳到一个空仓库页面，点 **uploading an existing file** 链接。

然后：

1. 先在本机把仓库包解开：解压 `dist\vedio-concentrator-repo.zip` 到任意文件夹
2. 打开那个文件夹，**全选里面的所有内容**（`README.md`、`LICENSE`、`scripts` 文件夹、`skill` 文件夹、`.gitignore`）
3. 拖进网页的上传框

> **关键**：是拖"文件夹里的内容"，不是拖"文件夹本身"。拖错了 GitHub 里会多套一层目录。

4. 下面 **Commit changes** 填一句说明，例如 `首次提交 v1.0.0`
5. 点 **Commit changes**

### 3. 验证

刷新仓库首页，应该看到：

```
README.md          ← 首页会自动显示它的内容
LICENSE
.gitignore
GITHUB-GUIDE.md
scripts/           ← 点进去有 10 个文件
skill/             ← 点进去有 2 个文件
```

README 渲染出来正常（有标题、有表格、有代码块）就说明对了。

### 4. 发 Release（重点！这步不做别人用不了）

1. 仓库页面右边栏点 **Releases** → **Create a new release**
2. **Choose a tag** 输入 `v1.0.0`，点 **Create new tag on publish**
3. **Release title** 填 `v1.0.0 首次发布`
4. **Describe this release** 随便写几句，例如：

   ```markdown
   ## 怎么用

   下载下面的 `vedio-concentrator-bundle.zip`，解压，双击 `install.cmd`。

   需要 Python 3.9+，首次安装会下载约 1.5 GB 语音模型。
   详细说明见 [README](README.md)。
   ```

5. **Attach binaries**：把 `dist\vedio-concentrator-bundle.zip` 拖进去
6. 点 **Publish release**

### 5. 验证 Release

回到仓库首页，右边栏会显示 Releases。点进去，**下载那个 zip，解压，双击 `install.cmd`** —— 当作自己是陌生人，完整走一遍。

这一步别省。这是唯一能确认"别人真的能装"的方法。

---

## 方法二：GitHub Desktop（推荐给新手，图形界面 + 能持续维护）

**适合**：想长期更新，但不想背 git 命令。
你机器上**已经装好了**（`%LOCALAPPDATA%\GitHubDesktop`）。

网页版改一个文件要重新上传一次，Desktop 只要点几下，日常维护靠它最舒服。

### 1. 准备本地文件夹

```powershell
# 建一个干净的工作目录，把源码解压进去
cd D:\X Files\DSH\dsh01
Expand-Archive .\vedio-concentrator\dist\vedio-concentrator-repo.zip -DestinationPath .\gh-publish -Force
```

### 2. 登录并创建仓库

1. 打开 **GitHub Desktop**
2. 菜单 **File → Add local repository**，选上一步的 `gh-publish` 文件夹
3. 它会说"这不是一个 git 仓库"，点 **create a repository** 链接
4. **Name** 填 `vedio-concentrator`，**Local path** 确认是那个文件夹
5. **Git ignore** 选 `None`（我们已经有 `.gitignore` 了，别让它覆盖）
6. 点 **Create repository**

### 3. 首次提交并发布

1. 左边会列出所有文件（都是绿色的 `+`，表示新增）
2. 左下角 **Summary** 填 `首次提交 v1.0.0`
3. 点 **Commit to main**
4. 顶上点 **Publish repository**
5. **取消勾选** "Keep this code private"（要公开），点 **Publish repository**

### 4. 去网页发 Release

Desktop 不会帮你发 Release，回到方法一的 **第 4 步**，在网页上发。

---

## 方法三：命令行（最快，适合以后自动化）

**适合**：愿意敲命令，或者想以后让脚本自动发布。

```powershell
# 1) 建仓库后，拿到地址（形如 https://github.com/Edoardo-Zhang/vedio-concentrator.git）

# 2) 进工作目录
cd D:\X Files\DSH\dsh01
Expand-Archive .\vedio-concentrator\dist\vedio-concentrator-repo.zip -DestinationPath .\gh-publish -Force
cd .\gh-publish

# 3) 初始化并提交
git init -b main
git add -A
git commit -m "首次提交 v1.0.0"

# 4) 连上远程仓库并推送
git remote add origin https://github.com/Edoardo-Zhang/vedio-concentrator.git
git push -u origin main
```

第 4 步会弹出登录窗口（因为你装了 Git Credential Manager）。选 **Sign in with your browser**，浏览器里点授权就行。**只需授权一次**，以后不再问。

推送成功的标志：

```
* [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

---

## 发布完成后检查清单

- [ ] 仓库首页 README 渲染正常，中文没乱码
- [ ] `scripts/` 下有 10 个文件，`skill/` 下有 2 个
- [ ] 有 Release，且 `vedio-concentrator-bundle.zip` 能下载
- [ ] **下载那个 zip 解压、双击 `install.cmd`，真的装上了**
- [ ] README 里 `Edoardo-Zhang` 的链接点开不 404
- [ ] 一行安装命令能跑（见下）

一行安装命令的验证（PowerShell）：

```powershell
$env:VC_REPO = "Edoardo-Zhang/vedio-concentrator"
irm https://raw.githubusercontent.com/Edoardo-Zhang/vedio-concentrator/main/scripts/bootstrap.ps1 | iex
```

---

## 后期维护

### 日常改代码的标准流程（4 步）

假设你改了 `scripts/v2mm.py`：

```powershell
# 1) 改完先重新打包（会同步更新 dist/ 里的两个 zip）
cd D:\X Files\DSH\dsh01\vedio-concentrator
python scripts\build_dist.py

# 2) 顺手自检一遍，别把坏的推上去
python scripts\setup_check.py

# 3) 提交
cd ..\gh-publish          # 你的克隆目录
# 把改动的文件复制过来，或直接在克隆目录里改
git add -A
git commit -m "修复：代理端口自动探测支持 IPv6"

# 4) 推送
git push
```

> ⚠️ **容易踩的坑**：`gh-publish`（或 GitHub Desktop 的本地目录）和
> `D:\X Files\DSH\dsh01\vedio-concentrator` 是**两份拷贝**。改了一份，另一份不会自动变。
>
> 两个办法选一个：
> - **简单**：以后只改 `gh-publish` 那份，改完把新版复制回工作区打包
> - **稳妥**：把 `gh-publish` 当成唯一仓库，`build_dist.py` 也在里面跑

### 改了代码要发新版本

版本号规则（看最后一位就行）：

| 改了什么 | 版本号 | 例子 |
|---|---|---|
| 修 bug | `v1.0.0` → `v1.0.1` | 修代理探测 |
| 加功能 | `v1.0.0` → `v1.1.0` | 加抖音支持 |
| 大改 / 不兼容 | `v1.0.0` → `v2.0.0` | 换掉 ASR 引擎 |

发新版：

1. `python scripts\build_dist.py` 重新打包
2. 改一下 `scripts/build_dist.py` 里的 `VERSION = "1.0.0"` → `"1.0.1"`
3. `git commit` + `git push`
4. 网页上 **Releases → Draft a new release**，tag 填 `v1.0.1`，传新的 bundle zip
5. Publish

**旧 Release 不要删**。有人可能正在用旧版，删了他的下载链接就断了。

### 只改文档（不用碰命令行）

GitHub 网页上直接点开 `README.md`，右上角铅笔图标 ✏️，改完拉到下面点 **Commit changes**。
适合改错别字、补充说明这种小事。

### 别人提问题（Issue）怎么处理

别人可以在你仓库的 **Issues** 页留言报 bug。建议：

1. 仓库 **Settings → Features** 里确认 Issues 是开的
2. 有人报 bug → 在本地复现 → 修 → 按上面的流程发新版
3. 修完在 Issue 里回复并 **Close issue**

### 提交前自检（避免把垃圾传上去）

`.gitignore` 已经帮你挡掉了这些东西，但你自己也要注意**永远不要提交**：

| 不要提交 | 为什么 |
|---|---|
| `*.mp4` `*.wav` `*.srt` | 你下载的视频和转写稿，动辄几百 MB，而且涉及版权 |
| `models/` 里的模型 | 1.5 GB，GitHub 单文件超 100 MB 直接拒绝 |
| `*.log` | 日志没用还占地方 |
| `dist/` 里的 zip | 可选。想让别人也能拿到 zip 就提交（40 KB 很小），不想就靠 Release |

检查当前会不会误传：

```powershell
git status              # 看哪些文件会被提交
git ls-files            # 看已经在仓库里的文件列表
```

如果发现大文件已经提交了，**别慌**，也别直接删了重来 —— 告诉我，我帮你清理历史。

### 常见故障

| 现象 | 原因 | 解决 |
|---|---|---|
| `git push` 报 `Authentication failed` | 凭据过期了 | 控制面板 → 凭据管理器 → Windows 凭据 → 删掉 `git:https://github.com`，重新 push 会再弹登录 |
| `git push` 报 `rejected - non-fast-forward` | GitHub 上有你本地没有的提交（比如你在网页上改过） | 先 `git pull --rebase`，再 `git push` |
| `git push` 一直卡住/超时 | 网络到 GitHub 不通 | 走代理：`git config --global http.proxy http://127.0.0.1:7897`；不需要时 `git config --global --unset http.proxy` |
| 网页上 README 中文乱码 | 文件编码不是 UTF-8 | 用 VS Code 打开，右下角编码选 **UTF-8**，另存 |
| 传上去发现少了文件 | 网页上传漏勾了 | 重新上传缺的那几个即可，不会覆盖已有的 |
| 想改仓库名 | — | Settings → Repository name 改完，**记得同步改 README 和 bootstrap.ps1 里的地址** |

---

## 你已经有的现成材料

不用从零准备，这些都在 `D:\X Files\DSH\dsh01\vedio-concentrator\dist\`：

| 文件 | 用途 |
|---|---|
| `vedio-concentrator-repo.zip` | **解开推到 GitHub**（方法一二三都用它） |
| `vedio-concentrator-bundle.zip` | **当 Release 附件**，给别人下载 |
| `SHA256SUMS.txt` | 校验值，可贴到 Release 说明里让人验证下载完整 |

两个包的区别：repo 包是给 `git push` 的，bundle 包顶层多两个安装脚本（`install.cmd` / `install.ps1`）方便陌生人不进子目录就能双击。功能完全一样。

---

## 一句话路线图

```
建仓库 → 推 repo 包 → 发 Release 传 bundle 包
   → 下载自己的 bundle 装一遍验证 → 以后改代码就 build → commit → push → 发新 Release
```
