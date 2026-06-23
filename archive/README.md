# archive/ — 参考资料,不参与运行/交付

本目录是**历史参考**,不是 active 代码:

- `1-Parse/`、`2-data_process/` — legacy 解析与 data_process 脚本。运行时正本已收进
  `cert_data_process/engines/`;这里保留作逻辑参考标准(见各自的 CLAUDE.md)。
- `ROADMAP.md` — 早期重构路线图。

**不进入交付包**(`.gitattributes` 里 `archive/ export-ignore`),也不被运行时引用。
改运行时行为请改 `cert_data_process/engines/`,不要改这里。
