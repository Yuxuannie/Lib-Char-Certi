# Guide screenshots

These images are referenced by [`../USER_GUIDE.md`](../USER_GUIDE.md). Each file
is currently a **grey placeholder frame** — replace it with a real screenshot from
your own certification run, keeping the same file name.

| File | Capture |
|------|---------|
| `01_setup.png` | Setup tab, configured, just before **Run certification** |
| `02_pipeline.png` | Pipeline tab during/after a run |
| `03_results.png` | Results tab with the basis radios visible |
| `04_pr_status.png` | PR Status pivot after **Build** |
| `05_outliers.png` | Outliers table after **Build** (Base basis) |
| `06_outlier_drill.png` | Outlier drill-down: scatter + source trace-back |
| `07_common.png` | Common offenders tab |
| `08_history.png` | History tab with completed runs |

After replacing the images, regenerate the shareable Word document
(`../USER_GUIDE.docx`):

```bash
python scripts/make_user_guide_doc.py
```
