# Demo Mode

Run:

```bash
./ai-stack demo
```

The command copies fictional engineering memory into:

```text
$AI_STACK_HOME/memory/engineering-memory/demo/
```

It also copies demo code repositories into:

```text
$AI_STACK_HOME/memory/code-memory/sample-python-app/
$AI_STACK_HOME/memory/code-memory/sample-repository-app/
```

Then it runs the existing memory and code indexers.

Clean only demo files with:

```bash
./ai-stack demo clean
```

This removes only the demo memory folder and demo code repositories committed
under `demo/code-memory/`.
