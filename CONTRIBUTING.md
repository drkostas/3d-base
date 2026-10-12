# Contributing

Issues and pull requests are welcome. If a picture looks wrong, please attach the mesh (or a small one that shows the same thing) and the command you ran.

```bash
python -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

Please add a test for every change in behaviour. Changes to the shading should keep the existing pictures identical unless the change is the point, because other tools compare these pictures from one run to the next.

## Writing for this repository

Everything here is public, including commit messages and pull request descriptions. Please write them for a user of the package. Do not name other projects, people or machines that use it, and keep real hostnames, IP addresses, paths and credentials out of code, tests and history (examples use `example.org` and `192.0.2.x`). A check on every pull request looks for terms that must not appear here.
