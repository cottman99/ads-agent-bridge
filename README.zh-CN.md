<p align="center">
  <a href="README.md">English</a> · <strong>简体中文</strong>
</p>

# ADS Agent Bridge

<p align="center">
  <strong>让通用 AI Agent 以本地、安全、版本感知的方式理解并操作 Keysight ADS。</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/ads-agent-bridge/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ads-agent-bridge"></a>
  <a href="https://pypi.org/project/ads-agent-bridge/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/ads-agent-bridge"></a>
  <a href="https://github.com/cottman99/ads-agent-bridge/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/cottman99/ads-agent-bridge/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/cottman99/ads-agent-bridge"></a>
</p>

![ADS Agent Bridge 将通用 Agent 与有边界的本地 EDA 环境连接起来](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/ads-agent-bridge-hero.png)

ADS Agent Bridge 是一个非官方、本地优先的 Keysight Advanced Design
System（ADS）文档与自动化桥接工具。它把用户机器上已有的 ADS 安装转化为：
版本感知的文档来源、边界明确的运行上下文，以及可由 Codex、OpenCode 等
通用 Agent 安全管理的自动化目标。

Agent 可以直接运行在 ADS 主机上，也可以通过 SSH 在远端执行 `ads-agent`。
实时 Bridge 端点仍只绑定在 ADS 主机的回环地址上，不会把 ADS 直接暴露到网络。

> [!IMPORTANT]
> 当前版本属于公开 Alpha。第一次使用时请采用一次性工作区，并在依赖自动化
> 结果前检查命令返回的能力门槛。Keysight 和 ADS 是 Keysight Technologies
> 的商标；本项目与 Keysight 没有隶属或官方背书关系。

## 你可以让 Agent 做什么

| 用户任务 | Bridge 能力 | 当前证据 |
| --- | --- | --- |
| “这台机器安装了哪些 ADS？这个版本具体能做什么？” | 自动发现多个版本、显式选择目标版本，并探测真实运行时能力。 | **Windows/Linux 已验证** |
| “查找这台机器所装 ADS 版本对应的正确 API。” | 通过 Portable Docs Skill 检索私有、按版本隔离的本地索引，并返回有界来源证据。 | **已验证；已做知识层对比** |
| “先证明 ADS Python 自动化能运行，不要碰我的工程。” | 创建一次性工作区、运行最小 AC 仿真，并通过独立门槛读取数据集。 | **Windows/Linux 已验证** |
| “打开这个准确的工作区，并告诉我 ADS 当前状态。” | 管理绑定工作区的 GUI 会话，核验进程、显示器、profile、所有权、UI 和模态状态。 | **Windows/Linux 已验证** |
| “使用我选中的原理图、版图、cell、cellview、文件夹或 DDS 对象。” | 随包交付的 DE/DDS 插件生成明确的 `ADS_CONTEXT`，无需猜测前台窗口。 | **真实 DE/DDS 会话已验证** |
| “观察这个长任务；安全时自动处理阻塞弹窗。” | 观察准确弹窗、获取目标截图，并按风险策略执行绑定新鲜指纹的动作。 | **维护中的弹窗门槛已验证；其他情况有界支持** |
| “断开连接但保留 ADS”，或“只关闭你启动的会话”。 | 将客户端断开与经过身份检查的原生安全退出分开。 | **Windows/Linux 已验证** |

首版能力刻意收敛，但它不是简单的命令包装器。文档、无 GUI 自动化、安装在
DE/DDS 内部的插件、弹窗监督和会话生命周期是相互独立、可观测的能力通路。
每项声明背后的准确机制、证据和停止规则见
[能力—机制—证据矩阵](docs/CAPABILITY_MATRIX.md)。

## DE/DDS 插件是产品的一等能力

`ads-agent setup` 会安装 Bridge 包及其可恢复的 ADS add-on。重启 ADS 后：

- **DE 原理图、版图和符号窗口：**右键菜单及 **Tools > ADS Context** 中提供
  **Copy ADS Context**；
- **DE Folder/Library 树：**对受支持的 workspace、folder、library、cell、
  cellview 以及多选对象提供 **Copy ADS Context**；
- **DDS：**右键菜单和 DDS 自己的顶层 **ADS Context** 菜单中提供
  **Copy ADS Context**，空白页面也可捕获。

DE 与 DDS 使用不同的入口和回调生命周期。复制出的 handle 只包含有界的目标与
选择信息，不包含端口、token，也不授予修改权限。Agent 在编辑、仿真、打开或关闭
任何对象前，仍必须检查上下文是否新鲜，并获得对应工作流的授权。准确约束见
[上下文交互契约](docs/CONTEXT_INTERACTION.md)。

## 工作原理

![ADS Agent Bridge 架构：双向本地文档检索、随包交付的 ADS 插件、有界实时 DE/DDS 控制，以及独立的无 GUI ADS Python 通路](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/how-it-works-image2.png)

产品包含三条主要执行通路：

1. **知识通路：**Portable Docs Skill 通过 CLI 将 Agent 的问题路由到所选 ADS
   安装对应的私有、按版本隔离的本地索引，并返回匹配内容和来源证据。
2. **实时 ADS 通路：**Session Manager 协调安装在 DE/DDS 内部的 ADS Agent
   Bridge 插件；仅绑定回环地址并使用随机 token 的端点会同时核验工作区、进程、
   显示器、slot、profile 和所有权。
3. **无 GUI 自动化通路：**使用所选 ADS Python 运行时创建一次性示例、执行仿真
   并读取数据集，不打开 ADS 主窗口。

Linux 上即使不打开 ADS 窗口，ADS Python 初始化仍可能需要可用的 X display。
隔离测试时保留真实用户 `HOME`，让 ADS 读取自己的用户状态；Bridge 的配置、缓存
和运行记录通过 `ADS_AGENT_HOME` 隔离。

## 证据与对比边界

Bridge 使用三类证据标签：

- **已验证（Validated）：**维护中的门槛已在真实 ADS 安装上通过；
- **已对比（Compared）：**该能力进入了已发布、隔离的对比测试；
- **有界可用（Available, bounded）：**公开接口存在并有明确停止规则，但不宣称
  普遍的无人值守正确性。

当前公开证据包含两组刻意收窄的对比：一组面向**知识通路**，另一组面向一个
**最小无 GUI 执行任务**。两者都没有比较安装、DE/DDS 插件、GUI 会话控制、
弹窗处理、DDS UI 读回、安全退出或双方完整产品面。

### ADS 2027 知识层基准——不是完整产品对比

![ADS Agent Bridge 与官方 ADS MCP 的知识层基准结果](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/ads2027-knowledge-benchmark.svg)

我们让两条知识通路在同一模型、主机、提示词和严格输出契约下，各自重复完成三项
ADS 知识任务三次。每次运行都隔离了全局 Agent 配置、skills、memory、rules 和
Shell 启动文件。

| 指标 | ADS Agent Bridge | 官方 ADS MCP |
| --- | ---: | ---: |
| 严格完成率 | **9/9（100%）** | 6/9（66.7%） |
| 总 token | **1,000,338** | 1,116,503 |
| 中位耗时 | 66.8 秒 | **63.5 秒** |
| 隔离违规 | 0 | 0 |

Bridge 总 token 少 10.4%，并完成全部九次任务；但速度并非全面领先：中位耗时高
5.2%，且一次几何任务形成了明显的均值长尾。在 Python DRC 任务中，官方 MCP 的
三次答案都采用未经验证的 `create_drc_job` 路径；Bridge 三次都给出已验证的能力
边界和安全回退方案。

这是一组小规模工程回归，不代表 Bridge 普遍优于官方 MCP，更不是完整产品对比；
早期试验也曾用于改进 Bridge 对这些已知问题的处理。详见
[测试方法与结论边界](https://github.com/cottman99/ads-agent-bridge/blob/main/docs/BENCHMARK_ADS2027_KNOWLEDGE.md)
和[脱敏后的逐次数据](https://github.com/cottman99/ads-agent-bridge/blob/main/docs/benchmarks/ads2027-knowledge-v1-summary.json)。

### ADS 2027 无 GUI 执行微基准

![ADS Agent Bridge 与官方 ADS MCP 的无 GUI AC 执行基准结果](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/ads2027-headless-ac-benchmark.svg)

我们还让双方各自使用已发布的执行入口，创建一次性 ADS 2027 工作区，在不打开
GUI 的情况下完成最小 AC 仿真、读取数据集并返回有限数值。Bridge 使用公开的
headless example / quickstart；官方 MCP 使用 `start_local_session` 和
`execute_python`。双方都禁止绕过产品入口直接从 Shell 调用 ADS Python 或仿真器。

| 指标 | ADS Agent Bridge | 官方 ADS MCP |
| --- | ---: | ---: |
| 首次完成率 | **3/3（100%）** | **3/3（100%）** |
| 总 token | **585,993** | 1,034,887 |
| 未缓存输入 token | **96,769** | 106,959 |
| 中位耗时 | **77.6 秒** | 98.9 秒 |
| 隔离违规 | 0 | 0 |

在这个单一任务中，Bridge 的总 token 少 43.4%，中位耗时低 21.5%。总 token
包含缓存输入；只计算未缓存输入时，差异为 9.5%。这只是三次重复的微基准，不是
普遍性能排名。详见
[执行方法、校准披露与结论边界](docs/BENCHMARK_ADS2027_HEADLESS_AC.md)
和[脱敏后的逐次数据](docs/benchmarks/ads2027-headless-ac-v1-summary.json)。

## 快速开始

前置条件：

- 本机或服务器上已安装并获得许可的 ADS；
- 用于运行 `ads-agent` 的 Python 3.10 或更高版本；
- Windows 或 Linux。

安装并验证本地环境：

```console
pipx install ads-agent-bridge
ads-agent doctor
ads-agent setup
ads-agent quickstart
```

`setup` 会自动发现 ADS 安装，不会固定某个版本。只有当文档索引与查询、插件注册、
一次性工作区创建、电路仿真和数据集读回全部通过时，`quickstart` 才返回成功。

通过上述门槛后，再打开真实工作区：

```console
ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk
ads-agent --pretty status
ads-agent disconnect                 # ADS 继续运行
ads-agent shutdown                   # 仅安全退出 Agent 拥有的会话
```

Linux GUI 会话应明确绑定目标显示器：

```console
ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk --display :4
```

<details>
<summary><strong>缺少 pipx 或系统 Python 版本过旧时的引导安装</strong></summary>

### Linux

```console
curl -fsSLO https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a30/install.sh
sh install.sh
```

### Windows PowerShell

```powershell
Invoke-WebRequest https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a30/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

引导脚本会搜索可用 Python，必要时创建隔离的 pipx 环境，不修改受系统管理的
Python。解释器选择、离线 wheel 和只检查模式见
[CLI 与安装参考](docs/CLI_REFERENCE.md)。

</details>

## 通过 SSH 远程使用

SSH 是当前推荐的远程边界。让公开 CLI 在 ADS 主机上执行，不要开放嵌入式 Bridge
端口：

```console
ssh ads-host 'ads-agent doctor'
ssh ads-host 'ads-agent --pretty status'
ssh ads-host 'ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk --display :4'
```

这样，session 文件、随机 token、进程所有权、工作区和 ADS 本身始终位于同一主机。
“本地客户端直接连接远端 Bridge”的正式协议和多客户端租约模型目前不属于公开契约。

## 安全与隐私

- 文档、索引、工作区、session token 和自动化结果默认留在本机或 ADS 服务器；
- Bridge 端点只监听回环地址，每个会话使用独立随机 token；
- 复用会话前必须匹配所选 ADS 实例和准确工作区，不会暗中切换工作区；
- 上下文 handle 只标识目标，不等于授权编辑或仿真；
- 弹窗动作绑定新鲜的进程与窗口指纹，不依赖产品标题或固定屏幕坐标；
- `shutdown` 拒绝未验证或用户拥有的会话，不强杀 ADS，也不静默丢弃修改；
- 任意嵌入式 Python 和动态 AEL 调用默认关闭，ADS 进程与客户端必须同时显式
  选择 unsafe 模式才会启用。

准确边界见[弹窗自动化契约](docs/DIALOG_AUTOMATION.md)、
[上下文交互契约](docs/CONTEXT_INTERACTION.md)和
[执行上下文契约](docs/EXECUTION_CONTEXT_CONTRACT.md)。

## ADS 版本支持

| ADS 版本 | 公开支持级别 |
| --- | --- |
| ADS 2025 及以后版本 | 稳定目标，最终由运行时能力探针决定 |
| ADS 2024 Update 2 | Preview |
| ADS 2023 Update 2 至 ADS 2024 Update 1 | Experimental |
| 更早版本 | 能发现本地文档时仅支持文档能力 |

Portable Docs Skill 不固定任何 ADS 版本；多个已安装版本可以自动发现并由用户显式选择。

## 五个公开示例

```console
ads-agent --pretty examples list
```

当前示例目录包括：

1. ADS 安装发现和显式版本选择；
2. 无 GUI 最小 AC 仿真与数据集读回；
3. 只读的实时 DE 工作区上下文；
4. 将 DDS 数据集有界读回到新的原生 DDS 文件；
5. 展示混合边界的固定只读 AEL 工作区调用。

每个示例都声明前置条件、状态变化、证据和停止规则。准确命令见
[EXAMPLES.md](docs/EXAMPLES.md)。

## 当前边界

本项目目前**没有**宣称已经完成 Momentum、RFPro、FEM、SIPro 或 PIPro 的完整
工作流，也没有提供公开的远端 Bridge 直连协议。当前支持通过 SSH 在服务器上执行
CLI；原始端口转发不是文档化的用户路径。这些能力必须通过独立的运行时和求解器侧
验收后，才能升级为正式支持。

## 文档

- [CLI 与安装参考](docs/CLI_REFERENCE.md)
- [能力—机制—证据矩阵](docs/CAPABILITY_MATRIX.md)
- [ADS 2027 无 GUI AC 执行基准](docs/BENCHMARK_ADS2027_HEADLESS_AC.md)
- [示例与验收门槛](docs/EXAMPLES.md)
- [发行契约](docs/RELEASE_CONTRACT.md)
- [会话与弹窗自动化](docs/DIALOG_AUTOMATION.md)
- [DE/DDS 上下文交互](docs/CONTEXT_INTERACTION.md)
- [执行上下文契约](docs/EXECUTION_CONTEXT_CONTRACT.md)
- [更新记录](CHANGELOG.md)

删除 ADS 集成但保留其他无关插件：

```console
ads-agent addon uninstall
```

## 开发

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。只有当对应测试、运行时观察或验收门槛真正
通过后，相关能力才会进入公开声明。
