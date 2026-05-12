# Crypto Research Assistant MVP

一个最小可用的「加密货币研究助手」示例：
- 接收用户问题
- 判断是否需要查询代币实时价格
- 调用 CoinGecko API 获取数据
- 将数据喂给 LLM 进行结构化总结
- 强制输出来源引用

## 1) 安装依赖

```bash
pip install -r requirements.txt
```

## 2) 配置环境变量

必需：
- `OPENAI_API_KEY`: OpenAI API Key

可选：
- `OPENAI_MODEL`: 模型名（默认 `gpt-4.1-mini`）

## 3) 运行

```bash
python agent.py "帮我看下 BTC 现在价格和24小时表现"
```

## 4) 说明

- 实时价格数据来源：CoinGecko Simple Price API
- 若问题包含价格相关意图且识别到币种（如 BTC/ETH/SOL），会触发 CoinGecko 查询
- 输出遵循结构化模板，并在文中与结尾附带来源引用
- 若缺少 `OPENAI_API_KEY`，脚本会返回最小兜底结构化响应，并提示如何启用完整分析
