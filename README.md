# cert_data_process

`cert_data_process` is the Phase 1 package skeleton for the library
characterization certification `data_process` flow. This first skeleton only
validates CLI/config input, materializes the empty output directory tree, and
writes run/compatibility manifests. Functional stages are intentionally added in
later PRs.

## Running without installation

In EDA environments where Python packaging build dependencies are unavailable,
run the skeleton directly from the repository:

```bash
python -m cert_data_process.cli --help
```

## Editable install note

The `pyproject.toml` console script uses the standard `setuptools.build_meta`
backend. Editable installation therefore requires `setuptools` to be available
in the Python environment:

```bash
python -m pip install -e .
cert_data_process --help
```

If the environment has no PyPI access and does not already provide
`setuptools`, use `python -m cert_data_process.cli` until the EDA image provides
the packaging backend locally.
