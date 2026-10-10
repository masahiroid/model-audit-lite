# Third-party notices

`model-audit-lite` is MIT-licensed (see `LICENSE`). The safeguard-bypass assets
under `attack_probes/` derive from the following third-party works, each used
under the MIT License. Their copyright notices are reproduced below as required.

## JailbreakBench artifacts

`attack_probes/wrappers.yaml` is generated from the JBC (manual) jailbreak
templates published in the JailbreakBench artifacts repository, with each
benchmark goal replaced by a `{behavior}` placeholder.

- Source: https://github.com/JailbreakBench/artifacts
- License: MIT

```
MIT License

Copyright (c) 2024 JailbreakBench Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## HarmBench

`attack_probes/fetch_behaviors.sh` downloads HarmBench behavior datasets at run
time (they are not redistributed in this repository).

- Source: https://github.com/centerforaisafety/HarmBench
- License: MIT — Copyright (c) 2024 centerforaisafety

## JailbreakBench behaviors

`attack_probes/fetch_behaviors.sh` also downloads the JailbreakBench behavior
dataset at run time (not redistributed here).

- Source: https://github.com/JailbreakBench/jailbreakbench
- License: MIT — Copyright (c) 2024 JailbreakBench Team
