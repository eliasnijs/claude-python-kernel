# claude-python-kernel

Gives Claude Code access to a persistent Python kernel. Variables defined in
the kernel are visible to scripts Claude runs. Variables defined in scripts do
not flow back into the kernel.

![screenshot](screenshot.png)

## how it works

Two execution layers:

```
kernel_exec(code)  →  exec(code, kernel_ns)          # writes persist
run_script(code)   →  exec(code, {**kernel_ns})       # writes die on return
```

The kernel runs as a Unix socket server (`/tmp/python-kernel-<name>.sock`).
It is started explicitly and persists across Claude Code sessions.

## files

```
kernel.py   kernel socket server
main.py     MCP server — bridges Claude Code to the kernel
tui.py      terminal UI to inspect running kernels
```

## usage

Start a kernel:

```sh
python kernel.py mykernel
```

Claude Code connects automatically via MCP. Available tools:

```
list_python_kernels     list running kernels
connect_python_kernel   attach to an existing kernel
spawn_python_kernel     start a new kernel
kill_python_kernel      shut down a kernel
kernel_exec             execute code in kernel namespace (persistent)
run_script              execute code with read access to kernel (isolated)
```

Inspect kernels with the TUI:

```sh
python tui.py
```

## install

Register the MCP server once:

```sh
claude mcp add -s user python-kernel python /path/to/main.py
```

## example

You're analyzing sales data across two regions. You load both datasets and your
internal analytics library into the kernel once — they stay resident across the
entire session.

> "Load the analytics codebase and both sales datasets into the kernel."

```python
# kernel_exec — load sources and codebase into kernel namespace
import sys
sys.path.insert(0, "/home/user/projects/analytics")
import analytics          # your editable local codebase

import pandas as pd
eu  = pd.read_parquet("data/sales_eu_2025.parquet")
us  = pd.read_parquet("data/sales_us_2025.parquet")
```

Claude can now query both datasets without reloading anything:

> "What are the top 5 products in the EU?"

```python
# run_script — reads kernel vars, result is returned but nothing persists
analytics.top_products(eu, n=5)
```

> "Compare revenue by category across both regions."

```python
# run_script — cross-source check
merged = pd.concat([eu.assign(region="eu"), us.assign(region="us")])
merged.groupby(["region", "category"])["revenue"].sum().unstack()
```

You spot a discrepancy and edit `analytics/metrics.py` to fix a margin
calculation. Because `analytics` is imported as an editable local package, you
can reload it in the kernel and immediately re-run the query — no restart, no
reload of the multi-GB parquet files:

> "I fixed the margin calculation in metrics.py, reload and rerun."

```python
# kernel_exec — hot-reload the fixed module
import importlib, analytics
importlib.reload(analytics)
```

The datasets stay in memory. Only the code changes.

You can also generate visualizations inline:

> "Plot monthly revenue trends for both regions."

```python
# run_script — plot revenue trends for both regions
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
for region, df in [("eu", eu), ("us", us)]:
    df.groupby("month")["revenue"].sum().plot(ax=ax, label=region)
ax.legend()
fig.savefig("revenue_by_region.png", dpi=150)
"revenue_by_region.png"
```

Claude saves the chart to disk and can read it back to inspect the output.

## isolation

`run_script` copies the kernel namespace shallowly before exec. Top-level name
assignments in scripts do not affect the kernel. Mutations to mutable objects
inside the kernel (lists, dicts) do propagate — this is intentional.
