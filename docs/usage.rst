Usage
=====

How it works
------------

Two execution layers:

.. code-block:: text

   kernel_exec(code)  →  exec(code, kernel_ns)       # writes persist
   run_script(code)   →  exec(code, {**kernel_ns})   # writes die on return

The kernel runs as a Unix socket server at ``/tmp/python-kernel-<name>.sock``.
It is started explicitly and persists across Claude Code sessions.

Files
-----

.. code-block:: text

   kernel.py   kernel socket server
   main.py     MCP server — bridges Claude Code to the kernel
   tui.py      terminal UI to inspect running kernels

Install
-------

Register the MCP server once:

.. code-block:: sh

   claude mcp add -s user python-kernel python /path/to/main.py

Start a kernel
--------------

.. code-block:: sh

   python kernel.py mykernel

Claude Code connects automatically via MCP. Available tools:

.. code-block:: text

   list_python_kernels     list running kernels
   connect_python_kernel   attach to an existing kernel
   spawn_python_kernel     start a new kernel
   kill_python_kernel      shut down a kernel
   kernel_exec             execute code in kernel namespace (persistent)
   run_script              execute code with read access to kernel (isolated)

Inspect kernels with the TUI:

.. code-block:: sh

   python tui.py

Example
-------

You're analyzing sales data across two regions. Load both datasets and your
analytics library into the kernel once — they stay resident across the session.

.. code-block:: python

   # kernel_exec — load sources and codebase into kernel namespace
   import sys
   sys.path.insert(0, "/home/user/projects/analytics")
   import analytics          # your editable local codebase

   import pandas as pd
   eu  = pd.read_parquet("data/sales_eu_2025.parquet")
   us  = pd.read_parquet("data/sales_us_2025.parquet")

Claude can now query both datasets without reloading anything:

.. code-block:: python

   # run_script — reads kernel vars, result is returned but nothing persists
   analytics.top_products(eu, n=5)

Hot-reload after a code change:

.. code-block:: python

   # kernel_exec — hot-reload the fixed module
   import importlib, analytics
   importlib.reload(analytics)

The datasets stay in memory. Only the code changes.

Isolation
---------

``run_script`` copies the kernel namespace shallowly before exec. Top-level
name assignments in scripts do not affect the kernel. Mutations to mutable
objects inside the kernel (lists, dicts) do propagate — this is intentional.
