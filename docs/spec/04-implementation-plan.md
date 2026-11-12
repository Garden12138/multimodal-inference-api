# 实施记录

以下阶段已在本仓库完成。测试均使用 Mock ComfyUI。

| 阶段 | 结果 |
|---|---|
| 0 盘点 | `docs/implementation-inventory.md`，工作流哈希已核对 |
| 1 规格与骨架 | `docs/spec/`、FastAPI 入口、配置 |
| 2 队列与 Provider | SQLite WAL、原子领取、`health/submit/poll/fetch_assets` |
| 3 视频独立化 | 不再调用 Studio；T2V、I2V、FLF 直接提交 8189 |
| 4 图片 API | 1024 与 2048，PNG 尺寸校验 |
| 5 鉴权与文件 | Bearer、CIDR、HMAC、路径约束 |
| 6 测试 | `python -m pytest`，23 项通过 |
| 7 部署与接入文档 | `scripts/`、`deploy/`、接入文档 |
| 8 本地 HTTP 验收 | 见实现报告。真实 GPU 生成未执行 |

未执行项保持阻塞，不记为通过：

- 104 上的真实 1024、2048、T2V、I2V、FLF
- 把流量从现有 8089 服务切到本服务
- Music3 推理
