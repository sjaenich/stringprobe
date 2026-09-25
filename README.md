# StringProbe paper artifact

The paper's source code is included in this repository:

- [`string-probe/compiler-provenance/`](string-probe/compiler-provenance/): feature and macro recovery.
- [`string-probe/feature-tests/`](string-probe/feature-tests/): experiments, ground truth, and evaluation. Entry points are in `scripts/`.
- [`string-probe/superc/`](string-probe/superc/): modified C preprocessor.

`artifact/` contains setup helpers. `configs/baseline.config` is the supplied
baseline Buildroot configuration.

## Run (Reproducibility not yet thoroughly tested)

Install Docker with Compose and Linux-container support. Run from this directory;
setup requires internet access. The image targets `linux/amd64`.

```sh
docker compose build
docker compose run --rm artifact prepare --module all --jobs 2
docker compose run --rm artifact run scripts.run_demo
```

Setup creates the required folders and matching Buildroot trees, applies the baseline configuration and package hooks, and builds the required packages.


```sh
docker compose run --rm artifact run scripts.run_demo_opt
docker compose run --rm artifact run scripts.run_demo_opt_os
```

Workspace files persist in the Compose workspace volume at `/workspaces/RevEng`;
results persist in the results volume at `/results`. Export results with:

```sh
mkdir -p results
docker compose run --rm -T --entrypoint tar artifact -C /results -cf - . | tar -xf - -C results
```

To inspect files or supply experiment inputs, open a container shell:

```sh
docker compose run --rm artifact bash
```

Full container execution has not yet been verified.