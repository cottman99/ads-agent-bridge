<p align="center">
  <a href="README.md">English</a> · <strong>简体中文</strong>
</p>

# ADS Agent Bridge

<p align="center">
  <strong>让 AI Agent 以本地、可验证、版本感知的方式理解并操作 Keysight ADS。</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/ads-agent-bridge/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ads-agent-bridge"></a>
  <a href="https://pypi.org/project/ads-agent-bridge/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/ads-agent-bridge"></a>
  <a href="https://github.com/cottman99/ads-agent-bridge/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/cottman99/ads-agent-bridge/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/cottman99/ads-agent-bridge"></a>
</p>

![ADS Agent Bridge 将通用 Agent 与有界的本地 EDA 环境连接起来](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/ads-agent-bridge-hero.png)

ADS Agent Bridge 是一个非官方、本地优先的 Keysight Advanced Design
System（ADS）文档与自动化桥接工具。它把用户机器上已有的 ADS 安装转化为：
版本感知的文档来源、边界明确的运行上下文，以及可被通用 Agent 安全管理的
自动化目标。Codex、OpenCode 等 Agent 不需要内置特定 ADS 模型。

Agent 可以运行在 ADS 主机上，也可以通过 SSH 在远端执行 `ads-agent`。
实时 Bridge 端点仍然只绑定在 ADS 主机的回环地址，不会把 ADS 直接暴露到网络。

> [!IMPORTANT]
> 当前版本属于公开 Alpha。第一次使用时请采用一次性工作区，并在依赖自动化
> 结果前检查命令返回的能力门槛。Keysight 和 ADS 是 Keysight Technologies
> 的商标；本项目与 Keysight 没有隶属或官方背书关系。

## 它能做什么

| 能力 | Agent 实际获得的能力 |
| --- | --- |
| ADS 自动发现 | 发现多个已安装 ADS 版本、让用户明确选择，并通过运行时探针判断能力，而不是默认使用最新版。 |
| 本地私有文档库 | 从用户本机已安装的官方文档构建按版本隔离的索引和 Markdown 缓存；项目不重新分发厂商文档。 |
| 可验证的快速入门 | 创建一次性工作区、运行最小 AC 仿真并读回数据集，每一步都有独立验收门槛。 |
| GUI 会话管理 | 打开指定工作区，跟踪进程、显示器和所有权，区分 Agent 启动的会话与用户已有会话。 |
| 精确 DE/DDS 上下文 | 在支持的菜单中加入 **Copy ADS Context**，让 Agent 从用户选中的工作区、设计、cell、cellview 或 DDS 目标出发，而不是猜测前台窗口。 |
| 有界 UI 生命周期 | 观察阻塞弹窗，执行经过身份校验的干预；断开连接时不关闭 ADS，只对已验证的 Agent 会话请求原生安全退出。 |

首版能力刻意收敛，但它不是简单的命令包装器：文档、无窗口自动化、DE/DDS
实时上下文、弹窗监督和会话生命周期是彼此独立且可观测的能力通路。

## ADS 2027 实测知识回归基准

![ADS Agent Bridge 与官方 ADS MCP 的基准结果](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/ads2027-knowledge-benchmark.svg)

我们让两条知识通路在同一模型、主机、提示词和严格输出契约下，各自重复完成
三项 ADS 知识任务三次。每次运行都隔离了全局 Agent 配置、skills、memory、
rules 和 Shell 启动文件。

| 指标 | ADS Agent Bridge | 官方 ADS MCP |
| --- | ---: | ---: |
| 严格完成率 | **9/9（100%）** | 6/9（66.7%） |
| 总 token | **1,000,338** | 1,116,503 |
| 中位耗时 | 66.8 秒 | **63.5 秒** |
| 隔离违规 | 0 | 0 |

Bridge 的总 token 少 10.4%，并完成了全部九次任务；但它并没有在速度上全面
领先：中位耗时高 5.2%，且一次几何任务形成了明显的均值长尾。在 Python DRC
任务中，官方 MCP 的三次答案都采用了未经验证的 `create_drc_job` 路径；Bridge
三次都给出了已验证的能力边界和安全回退方案。

这是一组小规模工程回归测试，不代表普遍优于官方 MCP：早期试验曾用于改进
Bridge 对这些已知问题的处理。详见[测试方法与结论边界](https://github.com/cottman99/ads-agent-bridge/blob/main/docs/BENCHMARK_ADS2027_KNOWLEDGE.md)
和[脱敏后的逐次数据](https://github.com/cottman99/ads-agent-bridge/blob/main/docs/benchmarks/ads2027-knowledge-v1-summary.json)。

## 快速开始

前置条件：

- 已在本机或服务器上安装并获得许可的 ADS；
- 用于运行 `ads-agent` 的 Python 3.10 或更高版本；
- Windows 或 Linux。

安装并验证本地环境：

```console
pipx install ads-agent-bridge
ads-agent doctor
ads-agent setup
ads-agent quickstart
```

`setup` 会自动发现 ADS 安装，不会固定某个版本。只有当文档索引与查询、插件
注册、一次性工作区创建、电路仿真和数据集读回全部通过时，`quickstart` 才会
返回成功。

通过上述门槛后，再打开真实工作区：

```console
ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk
ads-agent --pretty status
ads-agent disconnect                 # ADS 继续运行
ads-agent shutdown                   # 仅安全退出 Agent 拥有的会话
```

Linux GUI 会话应明确绑定到目标显示器：

```console
ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk --display :4
```

<details>
<summary><strong>缺少 pipx 或系统 Python 版本过旧时的引导安装</strong></summary>

### Linux

```console
curl -fsSLO https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a29/install.sh
sh install.sh
```

### Windows PowerShell

```powershell
Invoke-WebRequest https://github.com/cottman99/ads-agent-bridge/releases/download/v0.1.0a29/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

引导脚本会搜索可用的 Python，必要时创建隔离的 pipx 环境，不会修改受系统管理
的 Python。解释器选择、离线 wheel 和只检查模式见
[CLI 与安装参考](docs/CLI_REFERENCE.md)。

</details>

## 通过 SSH 远程使用

SSH 是当前推荐的远程边界。让公开 CLI 在 ADS 主机上执行，不要开放嵌入式
Bridge 端口：

```console
ssh ads-host 'ads-agent doctor'
ssh ads-host 'ads-agent --pretty status'
ssh ads-host 'ads-agent --pretty launch --workspace /path/to/MyWorkspace_wrk --display :4'
```

这样，session 文件、随机 token、进程所有权、工作区和 ADS 本身始终位于同一
主机。面向“本地客户端直接连接远端 Bridge”的正式协议以及多客户端租约模型，
目前还不属于公开契约。

## 工作原理

![ADS Agent Bridge 架构：双向本地文档检索、随包交付的 ADS 插件、有界实时 DE/DDS 控制，以及独立的无 GUI ADS Python 流程](https://raw.githubusercontent.com/cottman99/ads-agent-bridge/main/docs/assets/readme/how-it-works-image2.png)

产品包含三条主要执行通路：

1. **知识通路：**Portable Docs Skill 通过 CLI 把 Agent 的问题路由到所选 ADS
   安装对应的本地私有索引，并从索引取回匹配内容和来源证据。
2. **实时 ADS 通路：**Session Manager 连接随包交付并安装在 DE/DDS 内部的
   ADS Agent Bridge 插件；其仅绑定回环地址并使用随机 token 的端点同时核验
   工作区、进程、显示器、slot、profile 和所有权。
3. **无窗口自动化通路：**使用所选 ADS Python 运行时创建一次性示例、执行仿真
   并读取数据集，不打开 ADS 主窗口。

Linux 上即使不打开 ADS 窗口，ADS Python 初始化仍可能需要可用的 X display。
隔离测试时应保留真实用户 `HOME`，让 ADS 能看到自己的用户状态；Bridge 的
配置、缓存和运行记录通过 `ADS_AGENT_HOME` 隔离。

## 安全与隐私

- 文档、索引、工作区、session token 和自动化结果默认留在本机或 ADS 服务器。
- Bridge 端点只监听回环地址，每个会话使用独立随机 token。
- 复用会话前必须匹配所选 ADS 实例和精确工作区，不会暗中切换工作区。
- 上下文 handle 只标识目标，不等于授权编辑或仿真。
- 弹窗动作绑定到新鲜的进程和窗口指纹，不依赖产品标题或固定屏幕坐标。
- `shutdown` 拒绝未验证或用户拥有的会话，不强杀 ADS，也不静默丢弃修改。
- 任意嵌入式 Python 和动态 AEL 调用默认关闭，ADS 进程与客户端必须同时显式
  选择 unsafe 模式才会启用。

精确边界见[弹窗自动化契约](docs/DIALOG_AUTOMATION.md)、
[上下文交互契约](docs/CONTEXT_INTERACTION.md)和
[执行上下文契约](docs/EXECUTION_CONTEXT_CONTRACT.md)。

## ADS 版本支持

| ADS 版本 | 公开支持级别 |
| --- | --- |
| ADS 2025 及以后版本 | 稳定目标，最终由运行时能力探针决定 |
| ADS 2024 Update 2 | Preview |
| ADS 2023 Update 2 至 ADS 2024 Update 1 | Experimental |
| 更早版本 | 能发现本地文档时仅支持文档能力 |

Portable Docs Skill 不固定任何 ADS 版本；多个已安装版本可以被自动发现并由用户
明确选择。

## 五个公开示例

```console
ads-agent --pretty examples list
```

当前示例目录包括：

1. ADS 安装发现和明确版本选择；
2. 无窗口最小 AC 仿真与数据集读回；
3. 只读的实时 DE 工作区上下文；
4. 将 DDS 数据集有界读回到新的原生 DDS 文件；
5. 展示混合边界的固定只读 AEL 工作区调用。

每个示例都会声明前置条件、状态变化、证据和停止规则。准确命令见
[EXAMPLES.md](docs/EXAMPLES.md)。

## 当前边界

本项目目前**没有**宣称已经完成 Momentum、RFPro、FEM、SIPro 或 PIPro 的完整
工作流，也没有提供公开的远端 Bridge 直连协议。当前支持通过 SSH 在服务器上
执行 CLI；直接进行原始端口转发不是文档化的用户路径。这些能力必须通过独立的
运行时和求解器侧验收后，才能升级为正式支持。

## 文档

- [CLI 与安装参考](docs/CLI_REFERENCE.md)
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

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。只有当对应测试、运行时观测或验收门槛
真正通过后，相关能力才会进入公开声明。
