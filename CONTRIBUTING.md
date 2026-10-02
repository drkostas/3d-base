# Contributing

Issues and pull requests are welcome. If a picture looks wrong, please attach the mesh (or a small one that shows the same thing) and the command you ran.

```bash
python -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

Please add a test for every change in behaviour. Changes to the shading should keep the existing pictures identical unless the change is the point, because other tools compare these pictures from one run to the next.
