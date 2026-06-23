# Input folder

Put your real certification inputs here. The tool only **reads** these files; all
results are written under `./certi_runs`.

Suggested layout (any path works — you browse to it from the **Setup** tab):

```
input/
├── fmc/        # FMC reference data
└── lib/        # the characterized .lib files to certify
```

What `fmc/` should contain depends on the **FMC input** mode you pick in Setup:

| FMC input mode | `fmc/` contents | Note |
|----------------|-----------------|------|
| Decks (parse)  | raw FMC decks   | the tool parses them |
| Parsed DFDS    | parsed DFDS output | — |
| Parsed SCLD    | parsed SCLD golden | SCLD golden is in `ns` |

In the **Setup** tab, use the **FMC dir** and **Lib dir** browse buttons to point
at `input/fmc` and `input/lib`.

See [`../docs/USER_GUIDE.md`](../docs/USER_GUIDE.md) for the full walkthrough.
